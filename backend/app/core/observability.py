"""관측성(Observability) — Pydantic Logfire 계측(완전 선택적).

`configure_observability(app)` 는 다음 두 조건이 모두 만족될 때만 동작한다.
  1) `logfire` 패키지가 설치되어 있고,
  2) `settings.logfire_token`(env `LOGFIRE_TOKEN`) 이 설정되어 있을 때.
그 외(미설치·토큰 없음·계측 실패)에는 조용한 no-op 이므로 부팅을 절대 막지 않는다.
logfire 는 함수 내부에서 lazy-import 한다(미설치 환경에서도 import 가능).
"""
from __future__ import annotations

from typing import Any

from .config import settings
from .logging import get_logger

log = get_logger("macrolens.observability")


def configure_observability(app: Any) -> bool:
    """FastAPI 앱에 Logfire 계측을 시도. 적용되면 True, no-op 이면 False.

    실패가 부팅을 막지 않도록 모든 예외를 흡수한다.
    """
    token = getattr(settings, "logfire_token", "") or ""
    if not token:
        log.debug("logfire 토큰 미설정 → 관측성 비활성(no-op)")
        return False

    try:
        import logfire  # lazy-import: 미설치 환경에서도 모듈 import 가능
    except ImportError:
        log.debug("logfire 미설치 → 관측성 비활성(no-op)")
        return False

    try:
        logfire.configure(token=token, service_name="macrolens")
        logfire.instrument_fastapi(app)
        log.info("Logfire 관측성 활성화됨")
        return True
    except Exception as e:  # 설정/계측 실패는 부팅을 막지 않음
        log.warning("Logfire 설정 실패 → 비활성으로 계속: %s", e)
        return False
