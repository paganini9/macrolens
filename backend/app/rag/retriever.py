"""RAG Retriever — 검색(search) + 충분성(sufficiency) 판단. (interface_contracts v1)

설계 요점:
- `query()`는 검색 직전 `ensure_synced()`로 lazy 증분 동기화를 수행한다.
- macro_state(지표·값) + sectors 로 의미 검색 질의문을 구성해 3개 컬렉션을 검색한다.
- 가중치 매핑: `causal`(=w_causal) → kb_causal, `historical`(=w_historical) → kb_cases + kb_news.
  Chroma 거리(cosine distance)를 유사도(=1-distance)로 변환 후 컬렉션 가중치를 곱해
  전체에서 top-k 를 고른다.
- 섹터 메타 필터: 요청 sectors 와 hit 의 sectors 가 교집합이면 통과(sectors 비면 필터 없음).
- lead_lag / lag_window(시차)를 그대로 통과시켜 하류 노드가 타이밍에 활용한다.

충분성 규칙(FR-12, `is_sufficient` 참고):
- causal 타입 hit 가 1개 이상 존재하고,
- 요청 sectors 가 모두 어떤 hit 의 sectors 로 커버되면 충분.
- sectors 가 비어 있으면 hit 가 2개 이상이면 충분.

오프라인/테스트용으로는 Chroma 없이 동작하는 `MockRetriever`를 사용할 수 있다.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.core.types import Evidence, Source

from .chunking import meta_list
from .index import COLLECTIONS, Indexer

logger = get_logger(__name__)

# 컬렉션 → Evidence.type 매핑
_COLLECTION_TYPE = {
    "kb_causal": "causal",
    "kb_cases": "case",
    "kb_news": "news",
}


def _none_if_empty(v: Any) -> Optional[str]:
    """빈 문자열/None → None, 그 외 → str."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _build_query_text(macro_state: dict, sectors: list[str]) -> str:
    """macro_state(지표·값) + sectors 로 의미 검색 질의문을 구성.

    macro_state 의 다양한 형태(metrics 리스트/딕셔너리, indicators 리스트, flat dict)를
    견고하게 흡수해 '지표코드 값 단위' + 섹터를 공백으로 잇는다.
    """
    parts: list[str] = []

    def _add_metric(code: Any, value: Any = None, unit: Any = None) -> None:
        code_s = str(code).strip()
        if not code_s:
            return
        seg = code_s
        if value is not None and str(value).strip():
            seg += f" {value}"
        if unit is not None and str(unit).strip():
            seg += f" {unit}"
        parts.append(seg)

    if isinstance(macro_state, dict):
        # 1) metrics: list[Metric] 또는 dict[code -> Metric/value]
        metrics = macro_state.get("metrics") or macro_state.get("indicators")
        if isinstance(metrics, list):
            for m in metrics:
                if isinstance(m, dict):
                    _add_metric(m.get("code") or m.get("name"), m.get("value"), m.get("unit"))
                else:
                    _add_metric(m)
        elif isinstance(metrics, dict):
            for code, v in metrics.items():
                if isinstance(v, dict):
                    _add_metric(code, v.get("value"), v.get("unit"))
                else:
                    _add_metric(code, v)
        # 2) 보조: 명시적 질의/요약 텍스트가 있으면 포함
        for key in ("query", "summary", "regime", "context"):
            val = macro_state.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())

    for s in sectors or []:
        if str(s).strip():
            parts.append(str(s).strip())

    text = " ".join(parts).strip()
    return text or "거시 지표 섹터 영향"


def _indicators_in_state(macro_state: dict) -> set[str]:
    """macro_state 에 등장하는 지표 코드 집합(보조 필터/스코어용)."""
    codes: set[str] = set()
    if not isinstance(macro_state, dict):
        return codes
    metrics = macro_state.get("metrics") or macro_state.get("indicators")
    if isinstance(metrics, list):
        for m in metrics:
            if isinstance(m, dict):
                c = m.get("code") or m.get("name")
                if c:
                    codes.add(str(c))
            elif str(m).strip():
                codes.add(str(m).strip())
    elif isinstance(metrics, dict):
        codes.update(str(k) for k in metrics.keys())
    return codes


class ChromaRetriever:
    """ChromaDB 기반 Retriever (interface_contracts v1).

    내부적으로 `Indexer`를 소유하며(테스트용 주입 허용), 검색·충분성 판단·증분 동기화를 제공한다.
    """

    def __init__(self, indexer: Optional[Indexer] = None) -> None:
        self._indexer = indexer or Indexer()

    # --- 인덱싱 위임 ---
    def index_incremental(self) -> int:
        return self._indexer.index_incremental()

    def ensure_synced(self) -> None:
        self._indexer.ensure_synced()

    # --- 검색 ---
    def query(
        self,
        macro_state: dict,
        sectors: list[str],
        k: int = 6,
        weights: dict = {"causal": 0.5, "historical": 0.5},
    ) -> list[Evidence]:
        """거시 상태·섹터로 근거(Evidence)를 가중 검색해 top-k 반환.

        - 검색 전 `ensure_synced()` 로 lazy 증분 동기화.
        - causal/historical 가중치로 컬렉션별 유사도를 보정해 합산 정렬.
        - 결과 없음 → [] (예외 아님). Chroma 오류 → RetrievalError.
        """
        # 가중치 결정(미지정 시 settings)
        w = weights or {}
        w_causal = float(w.get("causal", settings.w_causal))
        w_hist = float(w.get("historical", settings.w_historical))
        coll_weight = {"kb_causal": w_causal, "kb_cases": w_hist, "kb_news": w_hist}

        sectors = [str(s).strip() for s in (sectors or []) if str(s).strip()]
        want_sectors = set(sectors)
        query_text = _build_query_text(macro_state, sectors)
        # 컬렉션별로 넉넉히 가져와 섹터 필터 후 합산(여유분 확보)
        n_fetch = max(k * 3, 12)

        try:
            self.ensure_synced()
            collections = self._indexer.collections
        except RetrievalError:
            raise
        except Exception as exc:  # noqa: BLE001 - 동기화/초기화 실패는 검색 오류로 승격
            logger.error("rag.retriever.sync_failed: %s", exc)
            raise RetrievalError(
                "지식 베이스 동기화에 실패했습니다. 잠시 후 다시 시도해 주세요.",
                internal_detail=f"ensure_synced/collections failed: {exc!r}",
            ) from exc

        scored: list[tuple[float, Evidence]] = []
        for coll_name in COLLECTIONS:
            coll = collections.get(coll_name)
            if coll is None:
                continue
            weight = coll_weight.get(coll_name, 0.0)
            if weight <= 0:
                continue
            try:
                count = coll.count()
            except Exception:  # noqa: BLE001
                count = 0
            if not count:
                continue
            try:
                res = coll.query(
                    query_texts=[query_text],
                    n_results=min(n_fetch, count),
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("rag.retriever.query_failed coll=%s: %s", coll_name, exc)
                raise RetrievalError(
                    "지식 베이스 검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                    internal_detail=f"collection.query failed coll={coll_name}: {exc!r}",
                ) from exc

            ids = (res.get("ids") or [[]])[0]
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]

            for i in range(len(ids)):
                meta = metas[i] or {}
                hit_sectors = meta_list(meta, "sectors")
                # 섹터 필터: 요청 sectors 가 있으면 교집합 필수
                if want_sectors and not (want_sectors & set(hit_sectors)):
                    continue
                dist = dists[i] if i < len(dists) and dists[i] is not None else 1.0
                sim = 1.0 - float(dist)  # cosine distance → 유사도
                score = sim * weight
                ev = self._to_evidence(coll_name, ids[i], docs[i] if i < len(docs) else "", meta)
                scored.append((score, ev))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [ev for _, ev in scored[:k]]

    @staticmethod
    def _to_evidence(coll_name: str, chunk_id: str, document: str, meta: dict) -> Evidence:
        """Chroma hit → Evidence dict 변환."""
        source: Source = {
            "title": str(meta.get("source_title", "") or ""),
            "url": str(meta.get("url", "") or ""),
            "ref": str(meta.get("path", "") or ""),
            "published_at": _none_if_empty(meta.get("published_at")),
        }
        ev: Evidence = {
            "id": str(meta.get("doc_id") or chunk_id),
            "type": _COLLECTION_TYPE.get(coll_name, "causal"),  # type: ignore[typeddict-item]
            "text": document or "",
            "sectors": meta_list(meta, "sectors"),
            "indicators": meta_list(meta, "indicators"),
            "lead_lag": _none_if_empty(meta.get("lead_lag")),
            "lag_window": _none_if_empty(meta.get("lag_window")),
            "source": source,
        }
        return ev

    # --- 충분성 ---
    def is_sufficient(self, hits: list[Evidence], sectors: list[str]) -> bool:
        """검색 결과 충분성 판단(FR-12).

        규칙:
        - causal 타입 hit 가 1개 이상 있고,
        - 요청 sectors 가 모두 어떤 hit 의 sectors 로 커버되면 True.
        - sectors 가 비어 있으면 hit 가 2개 이상이면 True.
        """
        return _is_sufficient_impl(hits, sectors)


def _is_sufficient_impl(hits: list[Evidence], sectors: list[str]) -> bool:
    if not hits:
        return False
    sectors = [str(s).strip() for s in (sectors or []) if str(s).strip()]
    if not sectors:
        return len(hits) >= 2
    has_causal = any(h.get("type") == "causal" for h in hits)
    if not has_causal:
        return False
    covered: set[str] = set()
    for h in hits:
        covered.update(h.get("sectors") or [])
    return all(s in covered for s in sectors)


# ---------------------------------------------------------------------------
# Mock — Chroma 불필요. 계약을 만족해 다른 레이어가 즉시 사용 가능.
# 픽스처는 실제 코퍼스 causal-0001 / causal-0003 형상을 반영.
# ---------------------------------------------------------------------------
_MOCK_EVIDENCE: list[Evidence] = [
    {
        "id": "causal-0001",
        "type": "causal",
        "text": (
            "정책금리(FFR)·장기금리(US10Y) 상승은 할인율을 높여 장기 현금흐름 비중이 큰 "
            "성장주·반도체 밸류에이션을 압박한다. 가격은 거의 동행해 반응하나, 반도체는 "
            "업황(수요·재고) 둔화가 더해질 때 실적이 수개월 후행해 추가 약세로 이어질 수 있다."
        ),
        "sectors": ["성장주", "반도체", "2차전지"],
        "indicators": ["FFR", "US10Y"],
        "lead_lag": "coincident",
        "lag_window": "0~1개월(가격), 3~6개월(실적)",
        "source": {
            "title": "2022 stock market decline",
            "url": "https://en.wikipedia.org/wiki/2022_stock_market_decline",
            "ref": "knowledge/causal/causal-0001.md",
            "published_at": None,
        },
    },
    {
        "id": "causal-0003",
        "type": "causal",
        "text": (
            "강달러(DXY 상승, 원/달러 상승)는 원화 환산 단가 개선으로 한국 수출 섹터"
            "(반도체·자동차)에 단기·부분적으로 우호적일 수 있다. 그러나 글로벌 수요 둔화·긴축과 "
            "동반될 때는 수요 위축이 단가효과를 압도해 수출·실적이 악화된다."
        ),
        "sectors": ["반도체", "자동차"],
        "indicators": ["DXY", "USDKRW"],
        "lead_lag": "leading",
        "lag_window": "1~2개월",
        "source": {
            "title": "South Korean Won — Historical Data",
            "url": "https://tradingeconomics.com/south-korea/currency",
            "ref": "knowledge/causal/causal-0003.md",
            "published_at": None,
        },
    },
]


class MockRetriever:
    """오프라인/테스트용 Retriever. Chroma 없이 계약을 만족.

    - `query`: 고정 픽스처(causal-0001/0003)를 요청 sectors 로 필터링해 top-k 반환.
      sectors 가 비면 전체 반환.
    - `is_sufficient`: ChromaRetriever 와 동일 규칙.
    """

    def query(
        self,
        macro_state: dict,
        sectors: list[str],
        k: int = 6,
        weights: dict = {"causal": 0.5, "historical": 0.5},
    ) -> list[Evidence]:
        want = {str(s).strip() for s in (sectors or []) if str(s).strip()}
        if not want:
            hits = list(_MOCK_EVIDENCE)
        else:
            hits = [e for e in _MOCK_EVIDENCE if want & set(e["sectors"])]
        return hits[:k]

    def is_sufficient(self, hits: list[Evidence], sectors: list[str]) -> bool:
        return _is_sufficient_impl(hits, sectors)

    def index_incremental(self) -> int:
        return 0

    def ensure_synced(self) -> None:
        return None


def get_retriever() -> ChromaRetriever:
    """기본 Retriever 팩토리. 기본은 ChromaRetriever.

    오프라인/테스트 환경에서는 `MockRetriever()`를 직접 생성해 사용할 수 있다(계약 동일).
    """
    return ChromaRetriever()
