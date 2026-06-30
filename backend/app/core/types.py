"""공유 타입 (interface_contracts v1). 모든 레이어가 import 한다."""
from __future__ import annotations
from typing import Literal, Optional, TypedDict


class Source(TypedDict):
    title: str
    url: str
    ref: str
    published_at: Optional[str]


class Metric(TypedDict):
    code: str
    value: float
    unit: str
    source: Source
    observed_at: str


class Evidence(TypedDict):
    id: str
    type: Literal["causal", "case", "news"]
    text: str
    sectors: list[str]
    indicators: list[str]
    lead_lag: Optional[str]
    lag_window: Optional[str]
    source: Source
