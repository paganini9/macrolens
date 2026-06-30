"""api_client 순수 로직 테스트 (SSE 파싱·이벤트 누적). Streamlit 비의존."""
from __future__ import annotations

from api_client import (
    BriefingState,
    iter_sse_events,
    make_history_entry,
    ranking_chart_rows,
    transition_chart_rows,
)

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


def test_transition_chart_rows_signs_and_magnitude():
    rows = transition_chart_rows([
        {"sector": "반도체", "direction": "negative", "strength": "high"},
        {"sector": "AI/SW", "direction": "positive", "strength": "medium"},
        {"sector": "금융", "direction": "neutral", "strength": "low"},
        {"sector": "자동차", "direction": "positive"},  # 강도 누락 → 기본 0.5
    ])
    by_sector = {r["sector"]: r for r in rows}
    assert by_sector["반도체"]["value"] == -1.0
    assert by_sector["AI/SW"]["value"] == 0.6
    assert by_sector["금융"]["value"] == 0.0  # neutral → 부호 0
    assert by_sector["자동차"]["value"] == 0.5
    assert by_sector["반도체"]["direction_label"] == "하락"


def test_ranking_chart_rows_sorted_desc():
    rows = ranking_chart_rows([
        {"sector": "A", "score": 0.3},
        {"sector": "B", "score": 0.9},
        {"sector": "C", "score": None},  # None → 0.0 방어
    ])
    assert [r["sector"] for r in rows] == ["B", "A", "C"]
    assert rows[-1]["score"] == 0.0


def test_make_history_entry_summary_and_truncation():
    state = BriefingState()
    state.summary = "한 줄 결론"
    entry = make_history_entry(state, "x" * 50, ts="2026-07-01 09:00")
    assert entry["summary"] == "한 줄 결론"
    assert entry["is_error"] is False
    assert len(entry["title"]) == 40 and entry["title"].endswith("…")
    assert entry["state"] is state


def test_make_history_entry_uses_error_message():
    state = BriefingState()
    state.error = {"user_message": "백엔드 연결 실패", "code": "NETWORK", "trace_id": ""}
    entry = make_history_entry(state, "질문", ts="2026-07-01 09:00")
    assert entry["is_error"] is True
    assert entry["summary"] == "백엔드 연결 실패"
