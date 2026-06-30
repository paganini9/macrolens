"""관측성(Logfire) 선택성 테스트 — 토큰/패키지 없으면 안전한 no-op 이어야 한다."""
from __future__ import annotations

import builtins

from app.core import observability
from app.core.observability import configure_observability


def test_noop_when_token_absent(monkeypatch):
    """토큰이 비어 있으면 logfire 를 건드리지 않고 False 반환(예외 없음)."""
    monkeypatch.setattr(observability.settings, "logfire_token", "", raising=False)
    assert configure_observability(app=object()) is False


def test_noop_when_logfire_missing(monkeypatch):
    """토큰이 있어도 logfire 미설치면 ImportError 를 흡수하고 False 반환."""
    monkeypatch.setattr(observability.settings, "logfire_token", "tok", raising=False)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "logfire" or name.startswith("logfire."):
            raise ImportError("logfire not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert configure_observability(app=object()) is False


def test_configure_does_not_raise(monkeypatch):
    """no-op 경로에서 어떤 예외도 발생하지 않아야 한다."""
    monkeypatch.setattr(observability.settings, "logfire_token", "", raising=False)
    # 반복 호출도 안전
    for _ in range(3):
        configure_observability(app=object())
