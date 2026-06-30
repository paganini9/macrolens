"""02 데이터 클라이언트/신뢰성 테스트.

네트워크 없이 주입 fetch(또는 monkeypatch)로 결정적 검증한다.
- 각 소스 클라이언트는 정상 응답 → 정규화 Metric, 오류 → None(gap)을 반환한다.
- 서킷 브레이커는 FMP 반복 실패 시 열려 폴백(CoinGecko)으로 라우팅된다.
"""
from __future__ import annotations

from app.core.exceptions import DataSourceError
from app.data import clients
from app.data.collector import LiveDataCollector

METRIC_KEYS = {"code", "value", "unit", "source", "observed_at"}
SOURCE_KEYS = {"title", "url", "ref", "published_at"}


def _assert_metric_shape(m) -> None:
    assert set(m.keys()) == METRIC_KEYS
    assert isinstance(m["value"], float)
    assert set(m["source"].keys()) == SOURCE_KEYS


# --- FRED -----------------------------------------------------------------
def test_fred_series_normalizes_metric():
    def fake_fetch(url, **kwargs):
        return {"observations": [{"date": "2024-06-01", "value": "5.33"}]}

    m = clients.fred_series("FFR", "FEDFUNDS", "%", api_key="K", fetch=fake_fetch)
    assert m is not None
    _assert_metric_shape(m)
    assert m["value"] == 5.33
    assert m["source"]["ref"] == "FEDFUNDS"
    assert m["observed_at"] == "2024-06-01"


def test_fred_series_none_without_key():
    def should_not_call(url, **kwargs):  # pragma: no cover
        raise AssertionError("키 없으면 fetch 금지")

    assert clients.fred_series("FFR", "FEDFUNDS", "%", api_key="", fetch=should_not_call) is None


def test_fred_series_none_on_fetch_error():
    def boom(url, **kwargs):
        raise DataSourceError("down", url)

    assert clients.fred_series("FFR", "FEDFUNDS", "%", api_key="K", fetch=boom) is None


def test_fred_series_none_on_missing_value():
    def dot(url, **kwargs):
        return {"observations": [{"date": "2024-06-01", "value": "."}]}

    assert clients.fred_series("FFR", "FEDFUNDS", "%", api_key="K", fetch=dot) is None


# --- ECOS -----------------------------------------------------------------
def test_ecos_latest_normalizes_metric():
    def fake_fetch(url, **kwargs):
        return {"StatisticSearch": {"row": [{"TIME": "20240601", "DATA_VALUE": "1378.5"}]}}

    m = clients.ecos_latest(
        "USDKRW", "731Y001", "0000001", "KRW", api_key="K", cycle="D", fetch=fake_fetch
    )
    assert m is not None
    _assert_metric_shape(m)
    assert m["value"] == 1378.5
    assert m["source"]["ref"] == "731Y001:0000001"


def test_ecos_latest_none_without_key():
    def should_not_call(url, **kwargs):  # pragma: no cover
        raise AssertionError("키 없으면 fetch 금지")

    assert clients.ecos_latest(
        "USDKRW", "731Y001", "0000001", "KRW", api_key="", fetch=should_not_call
    ) is None


def test_ecos_latest_none_on_fetch_error():
    def boom(url, **kwargs):
        raise DataSourceError("down", url)

    assert clients.ecos_latest(
        "KR_BASE", "722Y001", "0101000", "%", api_key="K", fetch=boom
    ) is None


# --- FMP ------------------------------------------------------------------
def test_fmp_quote_normalizes_metric():
    def fake_fetch(url, **kwargs):
        return [{"symbol": "BTCUSD", "price": 65000.0}]

    m = clients.fmp_quote("BTC", "BTCUSD", "USD", api_key="K", fetch=fake_fetch)
    assert m is not None
    _assert_metric_shape(m)
    assert m["value"] == 65000.0


def test_fmp_quote_none_without_key():
    def should_not_call(url, **kwargs):  # pragma: no cover
        raise AssertionError("키 없으면 fetch 금지")

    assert clients.fmp_quote("BTC", "BTCUSD", "USD", api_key="", fetch=should_not_call) is None


# --- CoinGecko (키리스) ----------------------------------------------------
def test_coingecko_price_normalizes_metric():
    def fake_fetch(url, **kwargs):
        return {"bitcoin": {"usd": 65000.0}}

    m = clients.coingecko_price("BTC", "bitcoin", "USD", fetch=fake_fetch)
    assert m is not None
    _assert_metric_shape(m)
    assert m["value"] == 65000.0
    assert m["unit"] == "USD"
    assert m["source"]["ref"] == "bitcoin"


def test_coingecko_price_none_on_fetch_error():
    def boom(url, **kwargs):
        raise DataSourceError("down", url)

    assert clients.coingecko_price("ETH", "ethereum", "USD", fetch=boom) is None


# --- 서킷 브레이커 + 폴백 -------------------------------------------------
def test_circuit_breaker_opens_fmp_and_falls_back_to_coingecko():
    """FMP 가 반복 실패하면 브레이커가 열려 더는 FMP 를 호출하지 않고
    CoinGecko 폴백으로 BTC 를 계속 해석한다."""
    fmp_calls = {"n": 0}

    def fetch(url, **kwargs):
        if "financialmodelingprep" in url:
            fmp_calls["n"] += 1
            raise DataSourceError("fmp down", url)
        if "coingecko" in url:
            return {"bitcoin": {"usd": 65000.0}}
        raise DataSourceError("unexpected", url)  # pragma: no cover

    import app.core.config as cfg
    cfg.settings.fmp_api_key = "FMPKEY"
    try:
        # fail_max=1: 첫 resolve 에서 FMP 실패 → 브레이커 open.
        c = LiveDataCollector(fetch=fetch, breaker_fail_max=1, breaker_reset_timeout=999)
        results = []
        for _ in range(4):
            c._cache.clear()  # 캐시 우회로 매번 소스까지 도달
            out = c.collect([], ["BTC"])
            results.append(out["BTC"]["value"])
    finally:
        cfg.settings.fmp_api_key = ""

    # 모든 회차 CoinGecko 폴백으로 정상 해석.
    assert results == [65000.0, 65000.0, 65000.0, 65000.0]
    # 첫 resolve(내부 재시도 포함)만 FMP 시도, 이후는 브레이커 차단 → FMP 미호출.
    assert fmp_calls["n"] >= 1
    assert fmp_calls["n"] < 4  # 4회 모두 시도했다면 폴백 라우팅 실패


def test_breaker_only_guards_configured_sources():
    """비대상 소스(FRED)는 브레이커를 생성하지 않는다(폴백 자체가 신뢰성 경로)."""
    c = LiveDataCollector()
    assert c._breaker_for("fred") is None
    assert c._breaker_for("fmp") is not None
