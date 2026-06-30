"""DataCollector 구현 (interface_contracts v1 §1).

- ``DataCollector``: runtime_checkable Protocol.
- ``LiveDataCollector``: cache-first + 소스 폴백 + 정규화. 결측은 결과에서 제외하고
  ``gaps()`` 로 별도 보고. ``collect()`` 시작 시 gaps 초기화.
- ``MockDataCollector``: 고정 픽스처(FFR/DXY/USDKRW)를 요청 지표로 필터해 반환.
  계약을 만족하는 mock 으로 다른 레이어가 지금 바로 사용.
- ``get_collector()``: 키가 하나도 없으면(이 환경 기본) Mock, 있으면 Live 선택.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.core.config import settings
from app.core.logging import get_logger
from app.core.types import Metric, Source
from app.data import clients
from app.data.cache import TTLCache
from app.data.clients import FetchFn, _default_fetch

logger = get_logger(__name__)


@runtime_checkable
class DataCollector(Protocol):
    """interface_contracts v1 §1 — 데이터 수집 계약."""

    def collect(self, market_scope: list[str], indicators: list[str]) -> dict[str, Metric]:
        """cache-first. 결측은 제외하고 gaps 는 별도 보고."""
        ...

    def gaps(self) -> list[str]:
        """직전 collect 에서 수집 실패한 지표 코드 목록."""
        ...


# ---------------------------------------------------------------------------
# 지표 → 소스 우선순위 레지스트리.
# 각 항목은 (source_name, params) 튜플 리스트. 앞에서부터 시도하고 성공 시 중단(폴백).
# 코인(BTC/ETH)은 섹터와 분리된 별도 지표로 취급.
# ---------------------------------------------------------------------------
INDICATOR_SPECS: dict[str, list[tuple[str, dict]]] = {
    "FFR": [("fred", {"series_id": "FEDFUNDS", "unit": "%"})],
    "US10Y": [("fred", {"series_id": "DGS10", "unit": "%"})],
    "DXY": [
        ("fred", {"series_id": "DTWEXBGS", "unit": "index"}),
        ("yfinance", {"symbol": "DX-Y.NYB", "unit": "index"}),
    ],
    "USDKRW": [
        ("fred", {"series_id": "DEXKOUS", "unit": "KRW"}),
        ("yfinance", {"symbol": "KRW=X", "unit": "KRW"}),
    ],
    "KR_BASE": [("ecos", {"stat_code": "722Y001", "item_code": "0101000", "unit": "%"})],
    "BTC": [
        ("fmp", {"symbol": "BTCUSD", "unit": "USD"}),
        ("coingecko", {"coin_id": "bitcoin", "unit": "USD"}),
    ],
    "ETH": [
        ("fmp", {"symbol": "ETHUSD", "unit": "USD"}),
        ("coingecko", {"coin_id": "ethereum", "unit": "USD"}),
    ],
}


class LiveDataCollector:
    """실데이터 수집기. 키/네트워크 부재 시 gap 으로 우아하게 강등."""

    def __init__(
        self,
        cache: Optional[TTLCache] = None,
        fetch: FetchFn = _default_fetch,
    ) -> None:
        self._cache: TTLCache = cache or TTLCache()
        self._fetch = fetch
        self._gaps: list[str] = []

    # -- 소스 디스패치 --------------------------------------------------
    def _call_source(self, code: str, source_name: str, params: dict) -> Optional[Metric]:
        """단일 소스 호출. 적절한 클라이언트로 위임하고 Metric|None 반환."""
        unit = params.get("unit", "")
        try:
            if source_name == "fred":
                return clients.fred_series(
                    code, params["series_id"], unit,
                    api_key=settings.fred_api_key, fetch=self._fetch,
                )
            if source_name == "ecos":
                return clients.ecos_latest(
                    code, params["stat_code"], params["item_code"], unit,
                    api_key=settings.ecos_api_key, fetch=self._fetch,
                )
            if source_name == "fmp":
                return clients.fmp_quote(
                    code, params["symbol"], unit,
                    api_key=settings.fmp_api_key, fetch=self._fetch,
                )
            if source_name == "yfinance":
                # 키리스, 라이브러리 자체 네트워킹 → fetch 주입 대상 아님
                return clients.yfinance_quote(code, params["symbol"], unit)
            if source_name == "coingecko":
                return clients.coingecko_price(
                    code, params["coin_id"], unit, fetch=self._fetch,
                )
        except Exception as exc:  # noqa: BLE001 - 어떤 소스 오류도 gap 으로
            logger.warning("소스 %s 호출 실패 %s: %s", source_name, code, exc)
            return None
        logger.warning("알 수 없는 소스 %s (%s)", source_name, code)
        return None

    def _resolve(self, code: str) -> Optional[Metric]:
        """지표 1개를 소스 우선순위에 따라 폴백 시도. 성공 시 Metric, 실패 시 None."""
        specs = INDICATOR_SPECS.get(code)
        if not specs:
            logger.info("미등록 지표 %s → gap", code)
            return None
        for source_name, params in specs:
            metric = self._call_source(code, source_name, params)
            if metric is not None:
                return metric
        return None

    # -- 계약 --------------------------------------------------------
    def collect(self, market_scope: list[str], indicators: list[str]) -> dict[str, Metric]:
        """요청 지표를 cache-first 로 수집. 결측은 제외하고 gaps 에 누적."""
        self._gaps = []  # collect 시작 시 초기화
        result: dict[str, Metric] = {}
        for code in indicators:
            cached = self._cache.get(code)
            if cached is not None:
                result[code] = cached
                continue
            metric = self._resolve(code)
            if metric is None:
                self._gaps.append(code)
                continue
            self._cache.set(code, metric)
            result[code] = metric
        return result

    def gaps(self) -> list[str]:
        return list(self._gaps)


# ---------------------------------------------------------------------------
# Mock — 계약 만족 픽스처. 다른 레이어가 지금 바로 사용하는 결정적 데이터.
# (deliverables/.../mocks/mock_metrics.json 의 형상을 그대로 미러. 명백히 'mock'.)
# ---------------------------------------------------------------------------
def _fixture(code: str, value: float, unit: str, title: str, ref: str, url: str,
             published_at: str, observed_at: str) -> Metric:
    return Metric(
        code=code,
        value=value,
        unit=unit,
        source=Source(title=title, url=url, ref=ref, published_at=published_at),
        observed_at=observed_at,
    )


MOCK_METRICS: dict[str, Metric] = {
    "FFR": _fixture(
        "FFR", 5.33, "%", "FRED FEDFUNDS", "FEDFUNDS",
        "https://fred.stlouisfed.org/series/FEDFUNDS",
        "2024-05-01", "2024-05-01",
    ),
    "DXY": _fixture(
        "DXY", 104.5, "index", "FRED DTWEXBGS", "DTWEXBGS",
        "https://fred.stlouisfed.org/series/DTWEXBGS",
        "2024-05-31", "2024-05-31",
    ),
    "USDKRW": _fixture(
        "USDKRW", 1378.5, "KRW", "FRED DEXKOUS", "DEXKOUS",
        "https://fred.stlouisfed.org/series/DEXKOUS",
        "2024-05-31", "2024-05-31",
    ),
}


class MockDataCollector:
    """고정 픽스처 기반 수집기. 요청 지표로 필터, 미보유 지표는 gap."""

    def __init__(self) -> None:
        self._gaps: list[str] = []

    def collect(self, market_scope: list[str], indicators: list[str]) -> dict[str, Metric]:
        self._gaps = []
        result: dict[str, Metric] = {}
        for code in indicators:
            metric = MOCK_METRICS.get(code)
            if metric is None:
                self._gaps.append(code)
                continue
            # 호출자 변형으로부터 픽스처 보호를 위해 복사본 반환
            result[code] = dict(metric)  # type: ignore[assignment]
        return result

    def gaps(self) -> list[str]:
        return list(self._gaps)


# ---------------------------------------------------------------------------
# 팩토리: 키 유무로 Live/Mock 명시 선택.
# ---------------------------------------------------------------------------
def _any_key_configured() -> bool:
    return bool(settings.fred_api_key or settings.ecos_api_key or settings.fmp_api_key)


def get_collector(force: Optional[str] = None) -> DataCollector:
    """DataCollector 팩토리.

    - ``force="mock"`` / ``"live"`` 로 강제 선택 가능(테스트/운영 토글).
    - 기본: 데이터 키(FRED/ECOS/FMP)가 하나도 없으면(현재 환경 기본) ``MockDataCollector``,
      하나라도 있으면 ``LiveDataCollector``. yfinance/coingecko 는 키리스라 선택 기준에서 제외.
    """
    if force == "mock":
        return MockDataCollector()
    if force == "live":
        return LiveDataCollector()
    if _any_key_configured():
        logger.info("데이터 키 감지 → LiveDataCollector")
        return LiveDataCollector()
    logger.info("데이터 키 없음 → MockDataCollector (계약 픽스처)")
    return MockDataCollector()
