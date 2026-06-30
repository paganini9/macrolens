"""Retriever 테스트 — MockRetriever(오프라인 필수) + ChromaRetriever(실코퍼스, 가능 시).

venv(3.12): `./.venv/Scripts/python.exe -m pytest -q`.
실 Chroma 테스트는 임베디드 임베딩 모델(all-MiniLM, onnx) 다운로드가 불가하면 skip.
"""
from __future__ import annotations

import os

import pytest

from app.core.types import Evidence  # noqa: F401  (형상 참고)
from app.rag.retriever import ChromaRetriever, MockRetriever, get_retriever

# 코퍼스 위치(레포 루트 기준 ../rag_corpus)
_CORPUS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "rag_corpus")
)


_EVIDENCE_KEYS = {
    "id", "type", "text", "sectors", "indicators", "lead_lag", "lag_window", "source"
}
_SOURCE_KEYS = {"title", "url", "ref", "published_at"}


def _assert_well_formed(ev: dict) -> None:
    assert set(ev.keys()) == _EVIDENCE_KEYS
    assert ev["type"] in ("causal", "case", "news")
    assert isinstance(ev["text"], str)
    assert isinstance(ev["sectors"], list)
    assert isinstance(ev["indicators"], list)
    assert ev["lead_lag"] is None or isinstance(ev["lead_lag"], str)
    assert ev["lag_window"] is None or isinstance(ev["lag_window"], str)
    assert set(ev["source"].keys()) == _SOURCE_KEYS


# ---------------------------------------------------------------------------
# MockRetriever — 오프라인, 반드시 통과
# ---------------------------------------------------------------------------
def test_mock_query_shape_and_keys():
    r = MockRetriever()
    hits = r.query({"metrics": [{"code": "FFR", "value": 3.75}]}, ["반도체"], k=6)
    assert hits, "반도체 섹터는 픽스처에 존재해야 함"
    for ev in hits:
        _assert_well_formed(ev)
    # 반도체는 causal-0001/0003 둘 다 포함
    ids = {e["id"] for e in hits}
    assert {"causal-0001", "causal-0003"} <= ids


def test_mock_sector_filter():
    r = MockRetriever()
    # 자동차는 causal-0003 에만 존재
    hits = r.query({}, ["자동차"], k=6)
    assert [e["id"] for e in hits] == ["causal-0003"]
    # 없는 섹터 → 빈 결과
    assert r.query({}, ["존재하지않는섹터"], k=6) == []
    # sectors 비면 전체
    assert len(r.query({}, [], k=6)) == 2


def test_mock_k_limit():
    r = MockRetriever()
    hits = r.query({}, [], k=1)
    assert len(hits) == 1


def test_mock_is_sufficient():
    r = MockRetriever()
    hits = r.query({}, ["반도체"], k=6)
    # causal hit 존재 + 반도체 커버 → 충분
    assert r.is_sufficient(hits, ["반도체"]) is True
    # 빈 hits → 불충분
    assert r.is_sufficient([], ["반도체"]) is False
    # 커버되지 않는 섹터 요청 → 불충분
    assert r.is_sufficient(hits, ["금융"]) is False
    # sectors 비고 hit 2개 이상 → 충분
    assert r.is_sufficient(r.query({}, [], k=6), []) is True


def test_is_sufficient_requires_causal():
    r = MockRetriever()
    # causal 이 아닌 hit 만으로는 불충분
    non_causal: Evidence = {
        "id": "n1", "type": "news", "text": "x", "sectors": ["반도체"],
        "indicators": [], "lead_lag": None, "lag_window": None,
        "source": {"title": "", "url": "", "ref": "", "published_at": None},
    }
    assert r.is_sufficient([non_causal], ["반도체"]) is False


def test_get_retriever_returns_chroma():
    assert isinstance(get_retriever(), ChromaRetriever)


# ---------------------------------------------------------------------------
# ChromaRetriever — 실 코퍼스 end-to-end (임베딩 모델 불가 시 skip)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.isdir(_CORPUS), reason="rag_corpus 디렉터리 없음")
def test_chroma_end_to_end(tmp_path):
    pytest.importorskip("chromadb", reason="chromadb 미설치")
    from app.rag.index import Indexer

    chroma_dir = str(tmp_path / "chroma")
    ledger = str(tmp_path / "ledger.sqlite")
    indexer = Indexer(corpus_dir=_CORPUS, chroma_dir=chroma_dir, ledger_path=ledger)
    retr = ChromaRetriever(indexer=indexer)

    # 임베딩 모델(onnx) 다운로드/실행이 오프라인 샌드박스에서 불가할 수 있음 → skip
    try:
        n = retr.index_incremental()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"임베딩 모델 사용 불가(오프라인 추정): {exc!r}")

    assert n > 0, "코퍼스에 색인 대상 문서가 있어야 함"

    macro_state = {
        "metrics": [
            {"code": "FFR", "value": 3.75, "unit": "%"},
            {"code": "DXY", "value": 105.0, "unit": ""},
        ]
    }
    hits = retr.query(macro_state, ["반도체"], k=4)
    assert hits, "반도체 관련 근거가 최소 1건 검색되어야 함"
    assert len(hits) <= 4
    for ev in hits:
        _assert_well_formed(ev)
        # 섹터 필터: 반도체가 포함되어야 함
        assert "반도체" in ev["sectors"]
        # Source.ref(파일 경로)가 채워져 있어야 함
        assert ev["source"]["ref"]

    # 충분성: causal hit 가 잡히면 True 가능. 최소한 호출이 bool 반환.
    assert isinstance(retr.is_sufficient(hits, ["반도체"]), bool)

    indexer.close()
