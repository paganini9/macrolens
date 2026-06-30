"""데이터 레이어 (02): 외부 소스 클라이언트·캐시·정규화.

공개 표면은 DataCollector 계약과 두 구현, 그리고 팩토리뿐.
다른 레이어는 ``get_collector()`` 로만 진입한다(내부 클라이언트 직접 호출 금지).
"""
from __future__ import annotations

from app.data.collector import (
    DataCollector,
    LiveDataCollector,
    MockDataCollector,
    get_collector,
)

__all__ = [
    "DataCollector",
    "LiveDataCollector",
    "MockDataCollector",
    "get_collector",
]
