"""RAG 검색 품질 평가 — precision@k · recall@k · MRR (가이드 4.4).

- 라벨링된 평가셋(`rag_corpus/_eval_set.jsonl`)의 각 질의를 `Retriever.query()` 로 실행해,
  기대 정답 문서 id(`relevant`)가 상위 k 에 들어오는지를 측정한다.
- Evidence.id 는 문서 id(doc_id)이므로 정답 매칭은 doc_id 기준.
- 평가는 기본적으로 **인과 지식(kb_causal) 중심**으로 수행(weights causal=1.0) — 핵심 KB 품질 측정.
  과거 사례/뉴스 포함 평가가 필요하면 weights 를 조정해 호출.
- 진입점: `python -m app.rag.eval` → 실제 코퍼스를 임시 인덱스로 빌드해 리포트 출력.

오프라인(임베디드 임베딩 모델 미가용)에서는 인덱싱이 불가할 수 있으므로,
`build_eval_retriever()` 는 예외를 그대로 전파한다(호출부/테스트가 skip 처리).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from .index import Indexer
from .retriever import ChromaRetriever

# 평가 기본값: 인과 KB 중심(historical 제외) · top-5.
DEFAULT_K = 5
DEFAULT_WEIGHTS: dict[str, float] = {"causal": 1.0, "historical": 0.0}


def _default_eval_path() -> str:
    """기본 평가셋 경로(레포 루트 rag_corpus/_eval_set.jsonl)."""
    here = os.path.dirname(os.path.abspath(__file__))
    # backend/app/rag → repo root(macrolens)/rag_corpus
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, "rag_corpus", "_eval_set.jsonl")


def load_eval_set(path: Optional[str] = None) -> list[dict[str, Any]]:
    """JSONL 평가셋 로드. 각 행: {query, macro_state, sectors, relevant[, k]}."""
    p = path or _default_eval_path()
    items: list[dict[str, Any]] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            items.append(json.loads(line))
    return items


# ---------------------------------------------------------------------------
# 지표 계산
# ---------------------------------------------------------------------------
def precision_at_k(hit_ids: list[str], relevant: set[str], k: int) -> float:
    topk = hit_ids[:k]
    if not topk:
        return 0.0
    found = sum(1 for h in topk if h in relevant)
    return found / float(len(topk))


def recall_at_k(hit_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    topk = set(hit_ids[:k])
    return len(topk & relevant) / float(len(relevant))


def reciprocal_rank(hit_ids: list[str], relevant: set[str]) -> float:
    for i, h in enumerate(hit_ids):
        if h in relevant:
            return 1.0 / float(i + 1)
    return 0.0


@dataclass
class EvalReport:
    n: int
    k: int
    precision_at_k: float
    recall_at_k: float
    mrr: float
    per_query: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "k": self.k,
            "precision_at_k": round(self.precision_at_k, 4),
            "recall_at_k": round(self.recall_at_k, 4),
            "mrr": round(self.mrr, 4),
        }


def evaluate(
    retriever: Any,
    eval_set: list[dict[str, Any]],
    k: int = DEFAULT_K,
    weights: Optional[dict[str, float]] = None,
) -> EvalReport:
    """평가셋 전체를 실행해 매크로 평균 precision@k·recall@k·MRR 산출."""
    weights = weights or DEFAULT_WEIGHTS
    p_sum = r_sum = mrr_sum = 0.0
    per_query: list[dict[str, Any]] = []
    for item in eval_set:
        sectors = list(item.get("sectors") or [])
        macro_state = item.get("macro_state") or {}
        relevant = set(item.get("relevant") or [])
        item_k = int(item.get("k") or k)
        # 정답 후보를 충분히 확보하도록 넉넉히 가져온 뒤 상위 k 로 지표 계산.
        hits = retriever.query(macro_state, sectors, k=max(item_k * 2, 10), weights=weights)
        hit_ids = [str(h.get("id")) for h in hits]
        p = precision_at_k(hit_ids, relevant, item_k)
        r = recall_at_k(hit_ids, relevant, item_k)
        rr = reciprocal_rank(hit_ids, relevant)
        p_sum += p
        r_sum += r
        mrr_sum += rr
        per_query.append(
            {
                "query": item.get("query", ""),
                "sectors": sectors,
                "relevant": sorted(relevant),
                "top": hit_ids[:item_k],
                "precision@k": round(p, 3),
                "recall@k": round(r, 3),
                "rr": round(rr, 3),
            }
        )
    n = len(eval_set) or 1
    return EvalReport(
        n=len(eval_set),
        k=k,
        precision_at_k=p_sum / n,
        recall_at_k=r_sum / n,
        mrr=mrr_sum / n,
        per_query=per_query,
    )


def build_eval_retriever(
    corpus_dir: Optional[str] = None,
    chroma_dir: Optional[str] = None,
    ledger_path: Optional[str] = None,
) -> ChromaRetriever:
    """실제 코퍼스를 (임시) Chroma 인덱스로 빌드한 ChromaRetriever 반환.

    chroma_dir 미지정 시 임시 디렉터리에 인덱스를 만든다(평가/테스트 격리용).
    인덱싱 실패(오프라인 임베딩 미가용)는 예외를 전파 — 호출부가 skip 처리.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    default_corpus = os.path.abspath(os.path.join(here, "..", "..", "..", "rag_corpus"))
    corpus = corpus_dir or default_corpus
    if chroma_dir is None:
        chroma_dir = tempfile.mkdtemp(prefix="rag_eval_chroma_")
    if ledger_path is None:
        ledger_path = os.path.join(chroma_dir, "ledger.sqlite")
    indexer = Indexer(corpus_dir=corpus, chroma_dir=chroma_dir, ledger_path=ledger_path)
    retr = ChromaRetriever(indexer=indexer)
    retr.index_incremental()
    return retr


def main() -> int:
    """`python -m app.rag.eval` — 임시 인덱스로 평가셋을 실행하고 리포트 출력."""
    eval_set = load_eval_set()
    try:
        retr = build_eval_retriever()
    except Exception as exc:  # noqa: BLE001
        print(f"[rag.eval] 인덱스 빌드 실패(오프라인 임베딩 추정): {exc!r}")
        return 1
    report = evaluate(retr, eval_set)
    print("=" * 64)
    print(f"[rag.eval] queries={report.n} k={report.k}")
    print(
        f"  precision@{report.k}={report.precision_at_k:.3f}  "
        f"recall@{report.k}={report.recall_at_k:.3f}  MRR={report.mrr:.3f}"
    )
    print("-" * 64)
    for q in report.per_query:
        print(
            f"  P={q['precision@k']:.2f} R={q['recall@k']:.2f} RR={q['rr']:.2f} "
            f"| {q['query'][:40]} | top={q['top']}"
        )
    print("=" * 64)
    try:
        retr._indexer.close()  # type: ignore[attr-defined]
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
