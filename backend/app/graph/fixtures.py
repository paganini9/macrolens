"""그래프 자가 테스트용 경량 fixture mock (계약 준수).

data/rag/store 실구현이 붙기 전까지 그래프를 독립적으로 E2E 완주시키기 위한 것.
canonical 값은 contracts/mocks/*.json 과 정합한다. 실서비스 결선(T-41/T-50)은
data.get_collector()/rag.get_retriever()/store.get_store() 를 주입한다.
"""
from __future__ import annotations

from app.core.types import Evidence, Metric

_METRICS: dict[str, Metric] = {
    "FFR": {"code": "FFR", "value": 4.5, "unit": "%",
            "source": {"title": "FOMC", "url": "https://example/fomc", "ref": "news/2026-06-30.md", "published_at": "2026-06-17"},
            "observed_at": "2026-06-30"},
    "DXY": {"code": "DXY", "value": 103.5, "unit": "index",
            "source": {"title": "DXY", "url": "https://example/dxy", "ref": "news/2026-06-30.md", "published_at": "2026-06-29"},
            "observed_at": "2026-06-30"},
    "USDKRW": {"code": "USDKRW", "value": 1545.0, "unit": "KRW",
               "source": {"title": "USDKRW", "url": "https://example/fx", "ref": "news/2026-06-30.md", "published_at": "2026-06-29"},
               "observed_at": "2026-06-30"},
}

_EVIDENCE: list[Evidence] = [
    {"id": "causal-0001", "type": "causal",
     "text": "금리 상승은 성장주·반도체 밸류에이션을 압박(가격 동행, 실적 후행).",
     "sectors": ["반도체", "성장주"], "indicators": ["FFR", "US10Y"],
     "lead_lag": "coincident", "lag_window": "0~1개월(가격)",
     "source": {"title": "causal-0001", "url": "", "ref": "knowledge/causal/causal-0001.md", "published_at": "2026-07-01"}},
    {"id": "causal-0003", "type": "causal",
     "text": "강달러는 한국 수출주에 양면적(단가 우호 vs 수요 둔화).",
     "sectors": ["반도체", "자동차"], "indicators": ["DXY", "USDKRW"],
     "lead_lag": "leading", "lag_window": "1~2개월",
     "source": {"title": "causal-0003", "url": "", "ref": "knowledge/causal/causal-0003.md", "published_at": "2026-07-01"}},
]


class FixtureCollector:
    """DataCollector 계약. 요청 지표 중 fixture 보유분만 반환, 나머지는 gap."""

    def __init__(self) -> None:
        self._gaps: list[str] = []

    def collect(self, market_scope: list[str], indicators: list[str]) -> dict[str, Metric]:
        self._gaps = []
        out: dict[str, Metric] = {}
        for code in indicators or list(_METRICS):
            if code in _METRICS:
                out[code] = _METRICS[code]
            else:
                self._gaps.append(code)
        return out

    def gaps(self) -> list[str]:
        return list(self._gaps)


class FixtureRetriever:
    """Retriever 계약. 섹터 교집합으로 필터한 fixture 근거 반환."""

    def query(self, macro_state: dict, sectors: list[str], k: int = 6, weights: dict | None = None) -> list[Evidence]:
        self.ensure_synced()
        if not sectors:
            return _EVIDENCE[:k]
        want = set(sectors)
        hits = [e for e in _EVIDENCE if want & set(e["sectors"])]
        return (hits or _EVIDENCE)[:k]

    def is_sufficient(self, hits: list[Evidence], sectors: list[str]) -> bool:
        if not hits:
            return False
        has_causal = any(h["type"] == "causal" for h in hits)
        return has_causal

    def index_incremental(self) -> int:
        return 0

    def ensure_synced(self) -> None:
        return None
