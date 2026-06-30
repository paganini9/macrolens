"""02 데이터 레이어 테스트. 네트워크 미접속(주입 fetch 모킹)으로 결정적 검증."""
from __future__ import annotations

from app.core.types import Metric
from app.data import (
    DataCollector,
    LiveDataCollector,
    MockDataCollector,
    get_collector,
)
from app.data.cache import TTLCache

METRIC_KEYS = {"code", "value", "unit", "source", "observed_at"}
SOURCE_KEYS = {"title", "url", "ref", "published_at"}


def _assert_metric_shape(m: Metric) -> None:
    """Metric / Source TypedDict 키 구조가 정확히 일치하는지 검증."""
    assert set(m.keys()) == METRIC_KEYS
    assert isinstance(m["value"], float)
    assert set(m["source"].keys()) == SOURCE_KEYS


# --- Mock -----------------------------------------------------------------
def test_mock_returns_expected_metrics():
    c = MockDataCollector()
    out = c.collect(["US", "KR"], ["FFR", "DXY", "USDKRW"])
    assert set(out.keys()) == {"FFR", "DXY", "USDKRW"}
    for m in out.values():
        _assert_metric_shape(m)
    assert out["FFR"]["unit"] == "%"
    assert c.gaps() == []


def test_mock_reports_gap_for_unknown_indicator():
    c = MockDataCollector()
    out = c.collect(["US"], ["FFR", "UNKNOWN_X"])
    assert set(out.keys()) == {"FFR"}
    assert c.gaps() == ["UNKNOWN_X"]


def test_mock_satisfies_protocol():
    assert isinstance(MockDataCollector(), DataCollector)
    assert isinstance(LiveDataCollector(), DataCollector)


# --- Live (주입 fetch, 네트워크 없음) -------------------------------------
def _fake_fred_response():
    return {"observations": [{"date": "2024-06-01", "value": "5.33"}]}


def test_live_normalizes_metric_with_injected_fetch():
    calls = {"n": 0}

    def fake_fetch(url, **kwargs):
        calls["n"] += 1
        return _fake_fred_response()

    # FRED 키가 있어야 클라이언트가 fetch 까지 도달 → settings 패치
    import app.core.config as cfg
    cfg.settings.fred_api_key = "TEST_KEY"
    try:
        c = LiveDataCollector(fetch=fake_fetch)
        out = c.collect(["US"], ["FFR"])
    finally:
        cfg.settings.fred_api_key = ""

    assert "FFR" in out
    _assert_metric_shape(out["FFR"])
    assert out["FFR"]["value"] == 5.33
    assert out["FFR"]["code"] == "FFR"
    assert out["FFR"]["source"]["ref"] == "FEDFUNDS"
    assert c.gaps() == []
    assert calls["n"] == 1


def test_live_records_gap_when_fetch_raises():
    def boom_fetch(url, **kwargs):
        raise RuntimeError("network down")

    import app.core.config as cfg
    cfg.settings.fred_api_key = "TEST_KEY"
    try:
        c = LiveDataCollector(fetch=boom_fetch)
        out = c.collect(["US"], ["FFR"])
    finally:
        cfg.settings.fred_api_key = ""

    assert out == {}
    assert c.gaps() == ["FFR"]


def test_live_records_gap_when_no_key():
    # 키 없음 → 네트워크 시도조차 없이 gap (graceful degradation)
    def should_not_call(url, **kwargs):  # pragma: no cover
        raise AssertionError("키 없을 때 fetch 호출되면 안 됨")

    c = LiveDataCollector(fetch=should_not_call)
    out = c.collect(["US"], ["FFR"])
    assert out == {}
    assert c.gaps() == ["FFR"]


def test_live_cache_first_avoids_second_fetch():
    calls = {"n": 0}

    def counting_fetch(url, **kwargs):
        calls["n"] += 1
        return _fake_fred_response()

    import app.core.config as cfg
    cfg.settings.fred_api_key = "TEST_KEY"
    try:
        c = LiveDataCollector(cache=TTLCache(ttl_seconds=999), fetch=counting_fetch)
        first = c.collect(["US"], ["FFR"])
        second = c.collect(["US"], ["FFR"])
    finally:
        cfg.settings.fred_api_key = ""

    assert first["FFR"]["value"] == second["FFR"]["value"]
    assert calls["n"] == 1  # 두 번째는 캐시 히트 → fetch 미호출
    assert c.gaps() == []


# --- 팩토리 ---------------------------------------------------------------
def test_factory_defaults_to_mock_without_keys():
    import app.core.config as cfg
    saved = (cfg.settings.fred_api_key, cfg.settings.ecos_api_key, cfg.settings.fmp_api_key)
    cfg.settings.fred_api_key = cfg.settings.ecos_api_key = cfg.settings.fmp_api_key = ""
    try:
        assert isinstance(get_collector(), MockDataCollector)
    finally:
        (cfg.settings.fred_api_key, cfg.settings.ecos_api_key, cfg.settings.fmp_api_key) = saved


def test_factory_uses_live_when_key_present():
    import app.core.config as cfg
    saved = cfg.settings.fred_api_key
    cfg.settings.fred_api_key = "X"
    try:
        assert isinstance(get_collector(), LiveDataCollector)
    finally:
        cfg.settings.fred_api_key = saved


def test_factory_force_overrides():
    assert isinstance(get_collector(force="mock"), MockDataCollector)
    assert isinstance(get_collector(force="live"), LiveDataCollector)
