"""Metric 정규화 헬퍼 (단일 진실 공급원).

모든 데이터 클라이언트는 이 모듈의 ``build_metric`` 으로만 ``Metric`` 을 만든다.
레이어마다 dict 모양을 제각각 만들지 않도록 강제 → 환각/형식 불일치 방지.
숫자(value)는 반드시 외부 소스에서 온 값이어야 한다(여기서 값을 지어내지 않는다).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.types import Metric, Source


def _now_iso() -> str:
    """UTC ISO8601 (초 단위) 타임스탬프."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_source(
    title: str,
    url: str,
    ref: str,
    published_at: Optional[str] = None,
) -> Source:
    """interface_contracts v1 의 Source TypedDict 를 생성."""
    return Source(title=title, url=url, ref=ref, published_at=published_at)


def build_metric(
    code: str,
    value: float,
    unit: str,
    source: Source,
    observed_at: Optional[str] = None,
) -> Metric:
    """interface_contracts v1 의 Metric TypedDict 를 생성.

    Args:
        code: 지표 코드(FFR, DXY, USDKRW 등).
        value: 외부 소스에서 온 수치. float 로 강제 변환한다.
        unit: 단위("%", "index", "KRW", "USD" 등).
        source: ``build_source`` 로 만든 출처.
        observed_at: 관측 시각(소스 기준). 없으면 호출 시각(UTC) 사용.
    """
    return Metric(
        code=code,
        value=float(value),
        unit=unit,
        source=source,
        observed_at=observed_at or _now_iso(),
    )
