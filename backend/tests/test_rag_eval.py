"""RAG precision@k 평가 게이트 + 지표 헬퍼 단위 테스트.

- 지표 헬퍼(precision/recall/MRR)는 오프라인에서 항상 검증.
- end-to-end 게이트: 실제 코퍼스를 임시 Chroma 인덱스로 빌드해 평가셋을 실행하고
  precision@5 임계치를 확인. 임베디드 임베딩 모델(all-MiniLM, onnx)이 오프라인에서
  로드 불가하면 깨끗이 skip(기본 경로를 먼저 시도 — 과거 환경에서는 가용했음).

CWD=backend: `./.venv/Scripts/python.exe -m pytest -q tests/test_rag_eval.py`.
"""
from __future__ import annotations

import os

import pytest

from app.rag.eval import (
    DEFAULT_WEIGHTS,
    evaluate,
    load_eval_set,
    precision_at_k,
    reciprocal_rank,
    recall_at_k,
)

# 레포 루트 기준 ../rag_corpus
_CORPUS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "rag_corpus")
)
_EVAL_SET = os.path.join(_CORPUS, "_eval_set.jsonl")

# 코퍼스가 실제로 충족하는(여유 있는) 임계치.
# 측정값: precision@5≈0.62, recall@5≈0.91, MRR≈0.95 (기본 all-MiniLM 임베딩).
PRECISION_AT_5_THRESHOLD = 0.50
RECALL_AT_5_THRESHOLD = 0.70
MRR_THRESHOLD = 0.60


# ---------------------------------------------------------------------------
# 지표 헬퍼 — 오프라인, 반드시 통과
# ---------------------------------------------------------------------------
def test_precision_recall_mrr_basics():
    relevant = {"a", "b"}
    hit_ids = ["a", "x", "b", "y", "z"]
    # top-2: a(O), x(X) → 1/2
    assert precision_at_k(hit_ids, relevant, 2) == pytest.approx(0.5)
    # top-3 에 a,b 모두 → recall 2/2
    assert recall_at_k(hit_ids, relevant, 3) == pytest.approx(1.0)
    # 첫 정답이 1위 → RR=1.0
    assert reciprocal_rank(hit_ids, relevant) == pytest.approx(1.0)


def test_metric_edge_cases():
    assert precision_at_k([], {"a"}, 5) == 0.0
    assert recall_at_k(["a"], set(), 5) == 0.0
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0
    # 첫 정답이 3위 → RR=1/3
    assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)


def test_eval_set_well_formed():
    items = load_eval_set(_EVAL_SET)
    assert 10 <= len(items) <= 20, "평가셋은 10~20개 질의여야 함"
    for it in items:
        assert it.get("query")
        assert isinstance(it.get("sectors"), list)
        assert it.get("relevant"), "각 질의는 정답 문서 id 가 있어야 함"


# ---------------------------------------------------------------------------
# end-to-end precision@k 게이트 — 임베딩 모델 불가 시 skip
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.isdir(_CORPUS), reason="rag_corpus 디렉터리 없음")
def test_precision_at_k_gate(tmp_path):
    pytest.importorskip("chromadb", reason="chromadb 미설치")
    from app.rag.eval import build_eval_retriever

    chroma_dir = str(tmp_path / "chroma")
    ledger = str(tmp_path / "ledger.sqlite")
    try:
        retr = build_eval_retriever(
            corpus_dir=_CORPUS, chroma_dir=chroma_dir, ledger_path=ledger
        )
    except Exception as exc:  # noqa: BLE001 - 오프라인 임베딩 미가용 추정
        pytest.skip(f"임베딩 모델 사용 불가(오프라인 추정): {exc!r}")

    try:
        eval_set = load_eval_set(_EVAL_SET)
        report = evaluate(retr, eval_set, k=5, weights=DEFAULT_WEIGHTS)
        assert report.n == len(eval_set)
        assert report.precision_at_k >= PRECISION_AT_5_THRESHOLD, (
            f"precision@5={report.precision_at_k:.3f} "
            f"< {PRECISION_AT_5_THRESHOLD} (report={report.as_dict()})"
        )
        assert report.recall_at_k >= RECALL_AT_5_THRESHOLD, report.as_dict()
        assert report.mrr >= MRR_THRESHOLD, report.as_dict()
    finally:
        try:
            retr._indexer.close()  # type: ignore[attr-defined]
        except Exception:
            pass
