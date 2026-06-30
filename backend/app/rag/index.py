"""RAG 인덱싱 — 파일 → ChromaDB(3 컬렉션) 멱등 증분 적재.

- PersistentClient(settings.chroma_dir), 컬렉션 kb_causal·kb_cases·kb_news.
- 임베딩(기본): Chroma 임베디드 all-MiniLM-L6-v2(onnxruntime) — API 키·추가 의존성 불필요.
- 임베딩(선택, 한·영 혼재 품질 개선): 환경변수 `MACROLENS_RAG_EMBED` 로 다국어
  sentence-transformers 모델(예: `e5`=intfloat/multilingual-e5-small, `bge-m3`)을 켤 수 있다.
  라이브러리/모델이 없으면 자동으로 기본 임베딩으로 graceful fallback(설치 강제 안 함).
  비기본 모델이 실제 활성화될 때만 `embed_model_version()` 이 바뀌어 ledger가 전체 재인덱싱을 트리거.
- 증분 판별: 각 파일 내용 해시(content hash) + 임베딩 모델 버전을 ledger(SQLite)에 보관.
  해시 동일 + 모델 동일 → skip, 그 외 → 해당 문서 청크 재임베딩 upsert.
- 진입점: `python -m app.rag.index` → index_incremental() 실행.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any, Optional

from app.core.config import settings

from .chunking import chunk_doc, collection_for
from .loader import iter_corpus_files, load_file

# 기본 임베딩 모델 버전 식별자(교체 시 전체 재인덱싱 트리거)
EMBED_MODEL_VERSION = "chroma-default-all-MiniLM-L6-v2"

COLLECTIONS = ("kb_causal", "kb_cases", "kb_news")

# 선택적 다국어 임베딩 별칭 → sentence-transformers 모델 id.
_EMBED_ALIASES = {
    "e5": "intfloat/multilingual-e5-small",
    "e5-small": "intfloat/multilingual-e5-small",
    "multilingual-e5-small": "intfloat/multilingual-e5-small",
    "bge-m3": "BAAI/bge-m3",
}
# 활성 임베딩(함수·버전) 1회 결정 후 캐시.
_embed_state: dict[str, Any] = {}


def _resolve_embedding() -> tuple[Any, str]:
    """활성 임베딩 함수와 버전 식별자를 (최초 1회) 결정해 캐시한다.

    환경변수 `MACROLENS_RAG_EMBED`:
    - 미설정/"default"/"minilm" → (None, 기본버전) ⇒ Chroma 임베디드 all-MiniLM 사용.
    - 별칭 또는 sentence-transformers 모델 id → 다국어 임베딩 함수 시도.
      sentence-transformers 미설치/모델 로드 실패 시 (None, 기본버전)으로 graceful fallback.
    fn 이 None 이면 컬렉션 생성 시 embedding_function 인자를 생략(=기본 임베딩).
    """
    if _embed_state:
        return _embed_state["fn"], _embed_state["version"]
    name = os.environ.get("MACROLENS_RAG_EMBED", "").strip()
    fn: Any = None
    version = EMBED_MODEL_VERSION
    if name and name.lower() not in ("default", "minilm", "all-minilm"):
        model_id = _EMBED_ALIASES.get(name.lower(), name)
        try:
            from chromadb.utils import embedding_functions as _ef  # 지연 import

            candidate = _ef.SentenceTransformerEmbeddingFunction(model_name=model_id)
            candidate(["health check"])  # 모델 실제 로드·임베딩 가능 여부 확인
            fn = candidate
            version = f"st::{model_id}"
        except Exception:  # noqa: BLE001 - 미설치/오프라인/로드실패 → 기본 폴백
            fn = None
            version = EMBED_MODEL_VERSION
    _embed_state["fn"] = fn
    _embed_state["version"] = version
    return fn, version


def embed_model_version() -> str:
    """활성 임베딩 모델 버전 식별자(ledger 비교용). 비기본 모델이 켜질 때만 값이 바뀐다."""
    return _resolve_embedding()[1]


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
        # API 가 그래프를 threadpool 에서 실행하므로(lifespan 인덱싱 ↔ 요청 쿼리 스레드 상이)
        # 단일 연결을 스레드 간 공유한다. 쓰기 직렬화는 _lock 으로 보호.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
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
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO rag_ledger(doc_id, path, hash, model_version, collection, chunk_ids)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    path=excluded.path, hash=excluded.hash, model_version=excluded.model_version,
                    collection=excluded.collection, chunk_ids=excluded.chunk_ids
                """,
                (doc_id, path, hash_, embed_model_version(), collection, ",".join(chunk_ids)),
            )
            self._conn.commit()

    def all_doc_ids(self) -> set[str]:
        cur = self._conn.execute("SELECT doc_id FROM rag_ledger")
        return {r[0] for r in cur.fetchall()}

    def delete(self, doc_id: str) -> Optional[dict[str, Any]]:
        prev = self.get(doc_id)
        with self._lock:
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
    """3 컬렉션 핸들 확보(없으면 생성).

    기본은 Chroma 임베디드 임베딩(all-MiniLM, onnx). `MACROLENS_RAG_EMBED` 로 다국어
    임베딩이 활성화되면 해당 embedding_function 을 주입(없으면 인자 생략=기본).
    """
    fn, _ = _resolve_embedding()
    out: dict[str, Any] = {}
    for name in COLLECTIONS:
        kwargs: dict[str, Any] = {"name": name, "metadata": {"hnsw:space": "cosine"}}
        if fn is not None:
            kwargs["embedding_function"] = fn
        out[name] = client.get_or_create_collection(**kwargs)
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
            if prev and prev.get("hash") == h and prev.get("model_version") == embed_model_version():
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
