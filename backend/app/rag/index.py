"""RAG 인덱싱 — 파일 → ChromaDB(3 컬렉션) 멱등 증분 적재.

- PersistentClient(settings.chroma_dir), 컬렉션 kb_causal·kb_cases·kb_news.
- 임베딩: Chroma 임베디드 기본(all-MiniLM-L6-v2, onnxruntime) — API 키 불필요.
- 증분 판별: 각 파일 내용 해시(content hash) + 임베딩 모델 버전을 ledger(SQLite)에 보관.
  해시 동일 + 모델 동일 → skip, 그 외 → 해당 문서 청크 재임베딩 upsert.
- 진입점: `python -m app.rag.index` → index_incremental() 실행.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from app.core.config import settings

from .chunking import chunk_doc, collection_for
from .loader import iter_corpus_files, load_file

# 임베딩 모델 버전 식별자(교체 시 전체 재인덱싱 트리거)
EMBED_MODEL_VERSION = "chroma-default-all-MiniLM-L6-v2"

COLLECTIONS = ("kb_causal", "kb_cases", "kb_news")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class IndexResult:
    upserted_docs: int
    upserted_chunks: int
    skipped_docs: int


# ----------------------------------------------------------------------------
# Ledger (SQLite) — 문서 id · 해시 · 임베딩 모델 버전 · 컬렉션 · 청크 id 목록
# ----------------------------------------------------------------------------
class Ledger:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_ledger (
                doc_id TEXT PRIMARY KEY,
                path TEXT,
                hash TEXT,
                model_version TEXT,
                collection TEXT,
                chunk_ids TEXT
            )
            """
        )
        self._conn.commit()

    def get(self, doc_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT doc_id, path, hash, model_version, collection, chunk_ids FROM rag_ledger WHERE doc_id=?",
            (doc_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "doc_id": row[0],
            "path": row[1],
            "hash": row[2],
            "model_version": row[3],
            "collection": row[4],
            "chunk_ids": (row[5] or "").split(",") if row[5] else [],
        }

    def upsert(self, doc_id: str, path: str, hash_: str, collection: str, chunk_ids: list[str]) -> None:
        self._conn.execute(
            """
            INSERT INTO rag_ledger(doc_id, path, hash, model_version, collection, chunk_ids)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(doc_id) DO UPDATE SET
                path=excluded.path, hash=excluded.hash, model_version=excluded.model_version,
                collection=excluded.collection, chunk_ids=excluded.chunk_ids
            """,
            (doc_id, path, hash_, EMBED_MODEL_VERSION, collection, ",".join(chunk_ids)),
        )
        self._conn.commit()

    def all_doc_ids(self) -> set[str]:
        cur = self._conn.execute("SELECT doc_id FROM rag_ledger")
        return {r[0] for r in cur.fetchall()}

    def delete(self, doc_id: str) -> Optional[dict[str, Any]]:
        prev = self.get(doc_id)
        self._conn.execute("DELETE FROM rag_ledger WHERE doc_id=?", (doc_id,))
        self._conn.commit()
        return prev

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Chroma 클라이언트 / 컬렉션
# ----------------------------------------------------------------------------
def get_client(chroma_dir: Optional[str] = None):
    """Chroma PersistentClient. (무거운 import는 함수 내부에서 — 샌드박스 보호)"""
    import chromadb  # 지연 import

    path = chroma_dir or settings.chroma_dir
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path)


def get_collections(client) -> dict[str, Any]:
    """3 컬렉션 핸들 확보(없으면 생성). 기본 임베딩 함수 사용(all-MiniLM, onnx)."""
    out: dict[str, Any] = {}
    for name in COLLECTIONS:
        out[name] = client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
    return out


class Indexer:
    """파일 → Chroma 증분 인덱서. RAG 레이어가 소유."""

    def __init__(self, corpus_dir: Optional[str] = None, chroma_dir: Optional[str] = None,
                 ledger_path: Optional[str] = None):
        self.corpus_dir = corpus_dir or settings.rag_corpus_dir
        self.chroma_dir = chroma_dir or settings.chroma_dir
        self.ledger_path = ledger_path or os.path.join(self.chroma_dir, "rag_ledger.sqlite")
        self._client = None
        self._collections: dict[str, Any] = {}
        self._ledger: Optional[Ledger] = None

    # --- lazy 핸들 ---
    @property
    def client(self):
        if self._client is None:
            self._client = get_client(self.chroma_dir)
        return self._client

    @property
    def collections(self) -> dict[str, Any]:
        if not self._collections:
            self._collections = get_collections(self.client)
        return self._collections

    @property
    def ledger(self) -> Ledger:
        if self._ledger is None:
            self._ledger = Ledger(self.ledger_path)
        return self._ledger

    # --- 증분 인덱싱 ---
    def index_incremental(self) -> int:
        """_manifest.csv + 파일 내용 해시 기준 신규/수정 문서를 upsert. 반환=upsert 문서 수."""
        result = self._run_incremental()
        return result.upserted_docs

    def _run_incremental(self) -> IndexResult:
        files = iter_corpus_files(self.corpus_dir)
        seen: set[str] = set()
        upserted_docs = 0
        upserted_chunks = 0
        skipped = 0
        for abs_path in files:
            with open(abs_path, "r", encoding="utf-8") as f:
                raw = f.read()
            h = content_hash(raw)
            doc = load_file(abs_path, self.corpus_dir)
            seen.add(doc.doc_id)
            prev = self.ledger.get(doc.doc_id)
            if prev and prev.get("hash") == h and prev.get("model_version") == EMBED_MODEL_VERSION:
                skipped += 1
                continue
            n = self._upsert_doc(doc, prev)
            self.ledger.upsert(
                doc.doc_id, doc.path, h, collection_for(str(doc.meta.get("type", "causal"))),
                self._last_chunk_ids,
            )
            upserted_docs += 1
            upserted_chunks += n
        # 코퍼스에서 사라진 문서 정리(삭제)
        self._prune_missing(seen)
        return IndexResult(upserted_docs, upserted_chunks, skipped)

    _last_chunk_ids: list[str] = []

    def _upsert_doc(self, doc, prev: Optional[dict[str, Any]]) -> int:
        chunks = chunk_doc(doc)
        coll_name = collection_for(str(doc.meta.get("type", "causal")))
        coll = self.collections[coll_name]
        # 이전 청크가 줄었을 수 있으니, 이전 ledger의 청크 id를 먼저 삭제
        if prev and prev.get("chunk_ids"):
            try:
                coll.delete(ids=[c for c in prev["chunk_ids"] if c])
            except Exception:
                pass
        ids = [c.chunk_id for c in chunks]
        docs = [c.text for c in chunks]
        metas = [c.meta for c in chunks]
        if ids:
            coll.upsert(ids=ids, documents=docs, metadatas=metas)
        self._last_chunk_ids = ids
        return len(ids)

    def _prune_missing(self, seen: set[str]) -> None:
        known = self.ledger.all_doc_ids()
        for doc_id in known - seen:
            prev = self.ledger.delete(doc_id)
            if prev and prev.get("collection") and prev.get("chunk_ids"):
                try:
                    self.collections[prev["collection"]].delete(
                        ids=[c for c in prev["chunk_ids"] if c]
                    )
                except Exception:
                    pass

    def ensure_synced(self) -> None:
        """검색 직전 lazy 증분 동기화. query()가 내부 호출."""
        self._run_incremental()

    def close(self) -> None:
        if self._ledger is not None:
            self._ledger.close()


def index_incremental() -> int:
    """모듈 레벨 헬퍼 — 기본 settings로 증분 인덱싱."""
    idx = Indexer()
    try:
        return idx.index_incremental()
    finally:
        idx.close()


def main() -> int:
    idx = Indexer()
    try:
        res = idx._run_incremental()
        print(
            f"[rag.index] corpus={idx.corpus_dir} chroma={idx.chroma_dir} "
            f"upserted_docs={res.upserted_docs} chunks={res.upserted_chunks} skipped={res.skipped_docs}"
        )
        return res.upserted_docs
    finally:
        idx.close()


if __name__ == "__main__":
    main()
