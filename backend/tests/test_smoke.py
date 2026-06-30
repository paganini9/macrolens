"""Phase 0 스모크: core 모듈 import·동작 확인. venv(3.12)에서 `pytest -q`."""
from app.core.config import settings
from app.core.exceptions import AppError, DataSourceError, GuardrailBlocked
from app.core.types import Metric, Evidence  # noqa: F401
from app.core.reliability import CircuitBreaker


def test_settings_defaults():
    assert settings.llm_provider in ("claude", "solar")
    assert 0.0 <= settings.w_causal <= 1.0


def test_error_to_dict():
    e = DataSourceError("일시적 데이터 오류, 잠시 후 재시도")
    d = e.to_dict(trace_id="abc123")
    assert d["code"] == "DATA_SOURCE_ERROR"
    assert d["trace_id"] == "abc123"
    assert issubclass(DataSourceError, AppError)
    assert GuardrailBlocked.http_status == 200


def test_circuit_breaker():
    cb = CircuitBreaker(fail_max=2, reset_timeout=999)
    assert cb.is_open is False
    cb.record_failure(); cb.record_failure()
    assert cb.is_open is True
    cb.record_success()
    assert cb.is_open is False
