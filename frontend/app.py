"""MacroLens Streamlit UI (07). 브리핑 카드 + 대화 하이브리드.

api_client.MacroLensClient 로 SSE 를 소비해 점진 렌더링한다.
표시 순서: 결론 → 전환신호 → 섹터 → 성장 랭킹 → 코인(분리) → 본문 → 출처.
색은 방향(상승/하락)에만 절제해 사용. 면책은 사이드바 상시 노출.
"""
from __future__ import annotations

import os

import streamlit as st

from api_client import SECTOR_UNIVERSE, BriefingState, MacroLensClient

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8200")
DISCLAIMER = "본 자료는 투자 권유가 아니며 판단 재료를 제공합니다."

DEPTH_LABELS = {"결론": "conclusion", "근거": "evidence", "배경": "background"}
DIR_BADGE = {"positive": "🟢 상승", "negative": "🔴 하락", "neutral": "⚪ 중립"}
STRENGTH_LABEL = {"high": "강", "medium": "중", "low": "약"}

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
    if "pins" not in ss:
        try:
            ss["pins"] = client.get_pins()
        except Exception:
            ss["pins"] = []


_init_state()


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

        # 3) 섹터 카드(전이)
        if state.transitions:
            st.subheader("섹터 영향")
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

        # 4) 성장 섹터 랭킹
        if state.ranking:
            st.subheader("성장 수혜 랭킹")
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
    new_pins = st.multiselect("핀", SECTOR_UNIVERSE, default=st.session_state["pins"], label_visibility="collapsed")
    if st.button("핀 저장", use_container_width=True):
        try:
            st.session_state["pins"] = client.set_pins(new_pins)
            st.toast("핀 저장됨")
        except Exception as e:
            st.error(f"핀 저장 실패: {e}")

    run_now = st.button("📋 지금 브리핑", type="primary", use_container_width=True)
    st.divider()
    st.caption(f"⚠️ {DISCLAIMER}")


# --- 메인 ------------------------------------------------------------------
st.header("월간 거시 점검 브리핑")

main_area = st.container()

if run_now:
    st.session_state["messages"].append(("user", "정기 브리핑 요청"))
    result = run_stream("이번 달 정기 거시 점검 브리핑을 작성해 줘", mode="briefing", body_container=main_area)
    st.session_state["last_briefing"] = result
elif st.session_state["last_briefing"] is not None:
    render_briefing(st.session_state["last_briefing"], main_area)
else:
    with main_area:
        st.info("좌측 **[지금 브리핑]** 을 누르거나 아래에 질문해 보세요.")
        st.caption("예: ‘FOMC 발표 후 한국 반도체·2차전지 영향은?’ · ‘만약 유가가 $100가 되면?’")

if run_now and st.session_state["last_briefing"] is not None:
    render_briefing(st.session_state["last_briefing"], main_area)


# --- 대화 ------------------------------------------------------------------
st.divider()
for role, text in st.session_state["messages"][-6:]:
    with st.chat_message(role):
        st.markdown(text)

prompt = st.chat_input("거시·섹터·코인에 대해 질문하기 (개별종목 매매 신호는 제공하지 않습니다)")
if prompt:
    st.session_state["messages"].append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        chat_area = st.container()
        result = run_stream(prompt, mode=None, body_container=chat_area)
        render_briefing(result, chat_area)
    st.session_state["last_briefing"] = result
    summary = result.summary or (result.error or {}).get("user_message", "")
    st.session_state["messages"].append(("assistant", summary or "(응답 없음)"))
