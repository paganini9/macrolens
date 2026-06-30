"""api_client 순수 로직 테스트 (SSE 파싱·이벤트 누적). Streamlit 비의존."""
from __future__ import annotations

from api_client import BriefingState, iter_sse_events

SAMPLE = [
    "event: status",
    'data: {"stage": "collect", "msg": "수집"}',
    "",
    "event: section",
    'data: {"kind": "sector", "payload": {"transitions": [{"sector": "반도체", "direction": "negative", "strength": "high", "rationale": "금리"}]}}',
    "",
    "event: section",
    'data: {"kind": "coin", "payload": {"coins": [{"ticker": "BTC", "direction": "negative", "note": "강달러"}]}}',
    "",
    "event: token",
    'data: {"text": "[결론] 방어적"}',
    "",
    "event: sources",
    'data: {"items": [{"title": "FOMC", "url": "http://x", "ref": "news/a.md"}]}',
    "",
    "event: done",
    'data: {"thread_id": "t1", "summary": "한 줄 결론", "trace_id": "tr1"}',
    "",
]


def test_iter_sse_events_parses_frames():
    events = list(iter_sse_events(SAMPLE))
    types = [e["type"] for e in events]
    assert types == ["status", "section", "section", "token", "sources", "done"]
    assert events[0]["stage"] == "collect"
    assert events[-1]["summary"] == "한 줄 결론"


def test_iter_sse_events_handles_missing_trailing_blank():
    lines = ["event: done", 'data: {"summary": "x"}']  # 끝 빈 줄 없음
    events = list(iter_sse_events(lines))
    assert events and events[0]["type"] == "done" and events[0]["summary"] == "x"


def test_iter_sse_events_skips_comments_and_bad_json():
    lines = [": keep-alive", "event: token", "data: not-json", ""]
    events = list(iter_sse_events(lines))
    assert events[0]["type"] == "token"
    assert events[0]["raw"] == "not-json"


def test_briefing_state_accumulates():
    state = BriefingState()
    for e in iter_sse_events(SAMPLE):
        state.apply(e)
    assert state.summary == "한 줄 결론"
    assert state.thread_id == "t1"
    assert state.trace_id == "tr1"
    assert state.transitions[0]["sector"] == "반도체"
    assert state.coins[0]["ticker"] == "BTC"
    assert "[결론]" in state.body
    assert state.sources[0]["title"] == "FOMC"
    assert state.error is None


def test_briefing_state_scenario_section():
    state = BriefingState()
    state.apply({"type": "section", "kind": "sector",
                 "payload": {"scenario": {"assumption": "유가 $100", "impacts": [], "uncertainty": "높음"}}})
    assert state.scenario["assumption"] == "유가 $100"
    assert state.transitions == []  # scenario 는 transitions 로 새지 않음


def test_briefing_state_error():
    state = BriefingState()
    state.apply({"type": "error", "code": "LLM_ERROR", "user_message": "일시적 오류", "trace_id": "z"})
    assert state.error["code"] == "LLM_ERROR"
    assert state.error["user_message"] == "일시적 오류"
