"""전환 탐지 (AC-A4). 직전 브리핑 대비 방향/강도 변화가 강조되는지 검증."""
from __future__ import annotations

from app.graph.build import build_graph
from app.graph.state import initial_state
from app.llm.provider import MockLLM
from app.store.mocks import MockStore


def _run(llm, store):
    app = build_graph(llm=llm, store=store)
    st = initial_state(thread_id="t-chg", user_input="FOMC 발표 후 점검")
    return list(app.stream(st))


def _changes(events):
    for e in events:
        if e["type"] == "section" and e["kind"] == "change":
            return e["payload"]["changes"]
    return []


def test_first_briefing_has_no_changes():
    store = MockStore()
    events = _run(MockLLM(), store)
    assert _changes(events) == []  # 직전 브리핑 없음


def test_second_briefing_flags_direction_flip():
    store = MockStore()
    _run(MockLLM(), store)  # 1회차: 반도체 negative 저장
    # 2회차: 반도체 방향 전환(positive)
    override = {
        "transition_analyzer": {
            "transitions": [
                {"sector": "반도체", "direction": "positive", "strength": "high",
                 "rationale": "메모리 사이클 반등 조짐", "uncertainty": "medium",
                 "evidence_ids": ["causal-0001"]},
            ]
        }
    }
    events = _run(MockLLM(overrides=override), store)
    changes = _changes(events)
    assert any(c["sector"] == "반도체" and "전환" in c["note"] for c in changes)
