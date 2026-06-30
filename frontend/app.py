"""MacroLens Streamlit UI (07). 브리핑 카드 + 대화 하이브리드.

api_client.MacroLensClient 로 SSE 를 소비해 점진 렌더링한다.
표시 순서: 결론 → 전환신호 → 섹터 → 성장 랭킹 → 코인(분리) → 본문 → 출처.
색은 방향(상승/하락)에만 절제해 사용. 면책은 사이드바 상시 노출.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from api_client import (
    SECTOR_UNIVERSE,
    BriefingState,
    MacroLensClient,
    make_history_entry,
    ranking_chart_rows,
    transition_chart_rows,
)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8200")
DISCLAIMER = "본 자료는 투자 권유가 아니며 판단 재료를 제공합니다."

DEPTH_LABELS = {"결론": "conclusion", "근거": "evidence", "배경": "background"}
DIR_BADGE = {"positive": "🟢 상승", "negative": "🔴 하락", "neutral": "⚪ 중립"}
STRENGTH_LABEL = {"high": "강", "medium": "중", "low": "약"}
# 방향에만 절제된 색(상승=초록·하락=빨강·중립=회색).
DIR_COLOR = {"상승": "#2e7d32", "하락": "#c62828", "중립": "#9e9e9e"}
EXAMPLE_PROMPTS = [
    "FOMC 발표 후 한국 반도체·2차전지 영향은?",
    "만약 유가가 $100가 되면 어떤 섹터가 수혜일까?",
    "달러 강세가 코인 시장에 주는 함의는?",
]

st.set_page_config(page_title="MacroLens", layout="wide")
client = MacroLensClient(BACKEND_URL)


# --- 세션 상태 초기화 -------------------------------------------------------
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("thread_id", None)
    ss.setdefault("market_scope", ["KR"])
    ss.setdefault("depth", "근거")
    ss.setdefault("messages", [])          # [(role, text)]
    ss.setdefault("last_briefing", None)   # BriefingState
    ss.setdefault("history", [])           # [make_history_entry(...)] 최신순
    ss.setdefault("view_idx", None)        # 히스토리에서 다시 보기 인덱스
    if "pins" not in ss:
        try:
            ss["pins"] = client.get_pins()
        except Exception:
            ss["pins"] = []


_init_state()


# --- 차트 헬퍼 --------------------------------------------------------------
def _transition_chart(transitions: list[dict]):
    """섹터 전이를 방향별 색의 가로 막대로 시각화(altair). 실패 시 표로 폴백."""
    rows = transition_chart_rows(transitions)
    if not rows:
        return
    df = pd.DataFrame(rows)
    try:
        import altair as alt

        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X("value:Q", title="영향(부호=방향 · 크기=강도)"),
                y=alt.Y("sector:N", sort="-x", title=None),
                color=alt.Color(
                    "direction_label:N",
                    title="방향",
                    scale=alt.Scale(
                        domain=list(DIR_COLOR.keys()),
                        range=list(DIR_COLOR.values()),
                    ),
                ),
                tooltip=["sector", "direction_label", "value"],
            )
            .properties(height=max(120, 32 * len(rows)))
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:  # altair 미가용 등 → 단순 표 폴백
        st.dataframe(df, use_container_width=True, hide_index=True)


def _ranking_chart(ranking: list[dict]):
    """성장 수혜 랭킹을 점수 막대로 시각화."""
    rows = ranking_chart_rows(ranking)
    if not rows:
        return
    df = pd.DataFrame(rows).set_index("sector")
    st.bar_chart(df, height=max(140, 32 * len(rows)), color="#1565c0")


# --- 렌더 헬퍼 --------------------------------------------------------------
def render_briefing(state: BriefingState, container) -> None:
    with container:
        if state.error:
            st.error(f"⚠️ {state.error['user_message']}")
            st.caption(f"trace_id: {state.error.get('trace_id', '')}")
            return

        # 1) 결론
        if state.summary:
            st.subheader("결론")
            st.markdown(f"**{state.summary}**")

        # 2) 전환 신호 배너
        if state.changes:
            st.markdown("**🔄 전환 신호**")
            for c in state.changes:
                st.warning(f"{c.get('sector', '')} — {c.get('note', '')}")

        # 3) 섹터 카드(전이) + 차트
        if state.transitions:
            st.subheader("섹터 영향")
            _transition_chart(state.transitions)
            cols = st.columns(2)
            for i, t in enumerate(state.transitions):
                with cols[i % 2]:
                    badge = DIR_BADGE.get(t.get("direction", "neutral"), "⚪")
                    strg = STRENGTH_LABEL.get(t.get("strength", ""), "")
                    st.markdown(f"**{t.get('sector', '')}** · {badge} (강도 {strg})")
                    st.caption(t.get("rationale", ""))
                    if t.get("uncertainty"):
                        st.caption(f"불확실성: {t['uncertainty']}")
                    if t.get("evidence_ids"):
                        st.caption("근거: " + ", ".join(t["evidence_ids"]))

        # 4) 성장 섹터 랭킹 + 차트
        if state.ranking:
            st.subheader("성장 수혜 랭킹")
            _ranking_chart(state.ranking)
            for r in state.ranking:
                st.markdown(f"- **{r.get('sector', '')}** ({r.get('score', 0):.2f}) — {r.get('rationale', '')}")

        # 5) 시나리오(what-if)
        if state.scenario:
            st.subheader("시나리오 가설")
            st.caption(state.scenario.get("assumption", ""))
            for imp in state.scenario.get("impacts", []):
                badge = DIR_BADGE.get(imp.get("direction", "neutral"), "⚪")
                st.markdown(f"- {imp.get('sector', '')} · {badge} · {imp.get('probability', '')} — {imp.get('rationale', '')}")
            if state.scenario.get("uncertainty"):
                st.info(f"불확실성: {state.scenario['uncertainty']}")

        # 6) 코인 (섹터와 분리)
        if state.coins:
            st.subheader("코인 (섹터와 분리)")
            for c in state.coins:
                badge = DIR_BADGE.get(c.get("direction", "neutral"), "⚪")
                st.markdown(f"- **{c.get('ticker', '')}** · {badge} — {c.get('note', '')}")

        # 7) 본문 + 출처
        if state.body:
            with st.expander("브리핑 전문", expanded=not state.transitions):
                st.markdown(state.body)
        if state.sources:
            st.markdown("**출처**")
            for s in state.sources:
                title = s.get("title", "") or s.get("ref", "")
                url = s.get("url", "")
                st.caption(f"- [{title}]({url})" if url else f"- {title} ({s.get('ref', '')})")


def run_stream(message: str, mode: str | None, body_container) -> BriefingState:
    """SSE 를 소비하며 상태 라인·본문을 라이브 갱신, 최종 BriefingState 반환."""
    state = BriefingState()
    status_ph = body_container.empty()
    body_ph = body_container.empty()
    try:
        for event in client.stream_chat(
            message,
            market_scope=st.session_state["market_scope"],
            depth=DEPTH_LABELS[st.session_state["depth"]],
            mode=mode,
            thread_id=st.session_state.get("thread_id"),
        ):
            state.apply(event)
            if event.get("type") == "status":
                status_ph.caption(f"⏳ {event.get('msg', '')} …")
            elif event.get("type") == "token":
                body_ph.markdown(state.body)
    except Exception as e:  # 연결 실패 등
        state.error = {"code": "NETWORK", "user_message": f"백엔드 연결에 실패했습니다 ({e}). 서버가 8200에서 실행 중인지 확인해 주세요.", "trace_id": ""}
    status_ph.empty()
    body_ph.empty()
    if state.thread_id:
        st.session_state["thread_id"] = state.thread_id
    return state


def record_briefing(state: BriefingState, query: str) -> None:
    """완료된 브리핑을 last_briefing + 세션 히스토리(최신순)에 기록."""
    st.session_state["last_briefing"] = state
    st.session_state["view_idx"] = None  # 새 결과 → 다시보기 해제
    entry = make_history_entry(state, query, ts=datetime.now().strftime("%m-%d %H:%M"))
    st.session_state["history"].insert(0, entry)
    del st.session_state["history"][20:]  # 최근 20건만 유지


# --- 사이드바 --------------------------------------------------------------
with st.sidebar:
    st.title("MacroLens")
    st.caption("거시 → 섹터·코인 전이 브리핑 (제안형)")

    try:
        h = client.health()
        st.success(f"backend ok · LLM={h.get('llm_provider')} · chroma={h.get('chroma')}")
    except Exception:
        st.error("backend 연결 불가 (8200)")

    st.session_state["market_scope"] = st.multiselect(
        "시장", ["KR", "US"], default=st.session_state["market_scope"]
    )
    st.session_state["depth"] = st.radio(
        "설명 깊이", list(DEPTH_LABELS.keys()),
        index=list(DEPTH_LABELS).index(st.session_state["depth"]), horizontal=True,
    )

    st.markdown("**관심 섹터(핀)**")
    new_pins = st.multiselect(
        "핀", SECTOR_UNIVERSE, default=st.session_state["pins"],
        label_visibility="collapsed", placeholder="섹터 선택…",
    )
    dirty = set(new_pins) != set(st.session_state["pins"])
    if st.button(
        "핀 저장" + (" •" if dirty else ""), use_container_width=True, disabled=not dirty,
        help="선택을 백엔드에 저장합니다.",
    ):
        try:
            st.session_state["pins"] = client.set_pins(new_pins)
            st.toast("핀 저장됨")
        except Exception as e:
            st.error(f"핀 저장 실패: {e}")
    if st.session_state["pins"]:
        st.caption("저장됨: " + " · ".join(st.session_state["pins"]))

    run_now = st.button("📋 지금 브리핑", type="primary", use_container_width=True)

    # 세션 히스토리(백엔드 비의존) — 과거 브리핑 다시 보기
    st.divider()
    st.markdown("**최근 브리핑**")
    history = st.session_state["history"]
    if not history:
        st.caption("아직 기록이 없습니다.")
    else:
        for i, entry in enumerate(history):
            icon = "⚠️" if entry["is_error"] else "📄"
            if st.button(
                f"{icon} {entry['ts']} · {entry['title']}",
                key=f"hist_{i}", use_container_width=True,
            ):
                st.session_state["view_idx"] = i
        if st.session_state["view_idx"] is not None and st.button(
            "↩ 최신으로", key="hist_clear", use_container_width=True
        ):
            st.session_state["view_idx"] = None

    st.divider()
    st.caption(f"⚠️ {DISCLAIMER}")


# --- 메인 ------------------------------------------------------------------
st.header("월간 거시 점검 브리핑")

main_area = st.container()

# 사이드바 예시 프롬프트 버튼 등으로 채워진 보류 질문
pending = st.session_state.pop("pending_prompt", None)

if run_now:
    st.session_state["messages"].append(("user", "정기 브리핑 요청"))
    result = run_stream("이번 달 정기 거시 점검 브리핑을 작성해 줘", mode="briefing", body_container=main_area)
    record_briefing(result, "정기 브리핑")
    render_briefing(result, main_area)
elif st.session_state["view_idx"] is not None:
    # 히스토리에서 과거 브리핑 다시 보기
    entry = st.session_state["history"][st.session_state["view_idx"]]
    with main_area:
        st.info(f"📄 과거 브리핑 다시 보기 · {entry['ts']} · {entry['title']}")
    render_briefing(entry["state"], main_area)
elif st.session_state["last_briefing"] is not None:
    render_briefing(st.session_state["last_briefing"], main_area)
else:
    with main_area:
        st.info("좌측 **[지금 브리핑]** 을 누르거나 아래에 질문해 보세요.")
        st.caption("아래 예시로 빠르게 시작할 수 있습니다.")
        ex_cols = st.columns(len(EXAMPLE_PROMPTS))
        for col, ex in zip(ex_cols, EXAMPLE_PROMPTS):
            if col.button(ex, key=f"ex_{ex}", use_container_width=True):
                st.session_state["pending_prompt"] = ex
                st.rerun()


# --- 대화 ------------------------------------------------------------------
st.divider()
for role, text in st.session_state["messages"][-6:]:
    with st.chat_message(role):
        st.markdown(text)

typed = st.chat_input("거시·섹터·코인에 대해 질문하기 (개별종목 매매 신호는 제공하지 않습니다)")
prompt = typed or pending
if prompt:
    st.session_state["messages"].append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        chat_area = st.container()
        result = run_stream(prompt, mode=None, body_container=chat_area)
        render_briefing(result, chat_area)
    record_briefing(result, prompt)
    summary = result.summary or (result.error or {}).get("user_message", "")
    st.session_state["messages"].append(("assistant", summary or "(응답 없음)"))
