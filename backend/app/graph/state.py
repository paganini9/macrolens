"""MacroLensState — 그래프 공유 상태 (contracts/state_schema.md FROZEN v1).

누적(append) vs 덮어쓰기(overwrite)를 반드시 준수한다.
- 누적 필드는 ``Annotated[list, operator.add]`` reducer 로 노드 반환값을 이어붙인다.
- 그 외 필드는 LangGraph 기본(마지막 값으로 덮어쓰기).

공유 타입(Source·Metric·Evidence)은 ``app/core/types.py`` 를 재사용하고,
그래프 내부 산출 타입(SectorTransition 등)만 여기서 정의한다.
"""
from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from app.core.types import Evidence, Metric, Source

# 섹터 유니버스 (D1, MVP 8) — 단일 진실 공급원.
SECTOR_UNIVERSE: list[str] = [
    "AI/SW",
    "반도체",
    "2차전지",
    "자동차",
    "금융",
    "에너지/화학",
    "바이오/헬스케어",
    "인터넷/플랫폼",
]

# 검색 루프 상한 N (종료 보장).
MAX_RETRIEVAL_ROUNDS: int = 2


# --- 그래프 내부 산출 타입 -------------------------------------------------
Direction = Literal["positive", "negative", "neutral"]
Strength = Literal["high", "medium", "low"]


class SectorTransition(TypedDict):
    sector: str
    direction: Direction
    strength: Strength
    rationale: str
    uncertainty: str
    evidence_ids: list[str]


class SectorScore(TypedDict):
    sector: str
    score: float
    rationale: str


class CoinImpact(TypedDict):
    ticker: str
    direction: Direction
    strength: Strength
    note: str
    evidence_ids: list[str]


class ChangeSignal(TypedDict):
    sector: str
    note: str


class BriefingResult(TypedDict):
    thread_id: str
    conclusion: str
    body: str
    sectors: list[SectorTransition]
    coins: list[CoinImpact]
    changes: list[ChangeSignal]
    disclaimer: str


class ScenarioImpact(TypedDict):
    sector: str
    direction: Direction
    rationale: str
    probability: str


class ScenarioResult(TypedDict):
    assumption: str
    impacts: list[ScenarioImpact]
    uncertainty: str


class Message(TypedDict):
    role: str
    content: str


class ErrorNote(TypedDict):
    node: str
    code: str
    detail: str


# --- 상태 ------------------------------------------------------------------
class MacroLensState(TypedDict, total=False):
    # 식별/입력
    thread_id: str                                      # 덮어쓰기(불변)
    intent: Literal["briefing", "whatif", "deepdive"]   # intent_router 출력
    trigger_type: Literal["event", "month_end", "on_demand"]
    user_input: str
    market_scope: list[str]                             # KR/US
    pinned_sectors: list[str]
    depth: Literal["conclusion", "evidence", "background"]

    # 데이터/충분성
    macro_data: dict[str, Metric]
    data_sufficient: bool
    data_gaps: Annotated[list[str], operator.add]       # 누적

    # 검색
    rag_context: list[Evidence]
    retrieval_round: int

    # 분석 산출
    transitions: list[SectorTransition]
    sector_ranking: list[SectorScore]
    coin_mapping: list[CoinImpact]
    changes: list[ChangeSignal]

    # 합성
    briefing: BriefingResult
    scenario_result: Optional[ScenarioResult]

    # 가드레일/안전
    blocked: bool
    safe_message: str

    # 추적 (누적)
    messages: Annotated[list[Message], operator.add]
    errors: Annotated[list[ErrorNote], operator.add]
    sources: Annotated[list[Source], operator.add]


def initial_state(
    *,
    thread_id: str,
    user_input: str,
    market_scope: Optional[list[str]] = None,
    pinned_sectors: Optional[list[str]] = None,
    depth: str = "evidence",
    intent: Optional[str] = None,
) -> MacroLensState:
    """API 입력 → 초기 상태. 누적 필드는 빈 리스트로 시작한다."""
    state: MacroLensState = {
        "thread_id": thread_id,
        "user_input": user_input,
        "market_scope": market_scope or ["KR"],
        "pinned_sectors": pinned_sectors or [],
        "depth": depth,  # type: ignore[typeddict-item]
        "retrieval_round": 0,
        "data_gaps": [],
        "messages": [],
        "errors": [],
        "sources": [],
        "blocked": False,
    }
    if intent:
        state["intent"] = intent  # type: ignore[typeddict-item]
    return state
