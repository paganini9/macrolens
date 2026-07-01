"""그래프 조립 + GraphApp.stream (interface_contracts v1 §5).

LangGraph StateGraph 로 노드·라우팅을 구성하고, ``GraphApp`` 가 컴파일된 그래프를
실행하며 노드 산출을 **SSE 이벤트**(status|section|token|sources|done|error)로 1:1 변환한다.

라우팅 3원칙:
- 완전성: 모든 분기 키가 목적지를 가진다.
- 배타성: 라우터는 단일 키를 반환한다(temp=0 분기와 결합해 재현성).
- 종료보장: 검색 루프는 retrieval_round 상한 N 에서 강제 전진한다.
"""
from __future__ import annotations

from typing import Iterator

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.types import Source
from app.llm import prompts

from .nodes import Nodes, briefing_prompt, build_briefing
from .state import MAX_RETRIEVAL_ROUNDS, MacroLensState
from .fixtures import FixtureCollector, FixtureRetriever

logger = get_logger(__name__)

# 노드 → 진행 단계(status.stage) 매핑.
_ACCUMULATORS = ("data_gaps", "messages", "errors", "sources")


# --- 라우터 ----------------------------------------------------------------
def route_safety(state: MacroLensState) -> str:
    return "blocked" if state.get("blocked") else "ok"


class _Router:
    """retriever.is_sufficient 를 보고 루프/전진을 결정(deps 필요)."""

    def __init__(self, retriever) -> None:
        self.retriever = retriever

    def route_retrieval(self, state: MacroLensState) -> str:
        hits = state.get("rag_context", []) or []
        sectors = state.get("pinned_sectors") or []
        try:
            sufficient = self.retriever.is_sufficient(hits, sectors)
        except AppError:
            sufficient = bool(hits)
        rnd = state.get("retrieval_round", 0)
        if not sufficient and rnd < MAX_RETRIEVAL_ROUNDS:
            return "retry"
        if state.get("intent") == "whatif":
            return "scenario"
        if not state.get("data_sufficient", True) or not hits:
            return "insufficient"
        return "analyze"


def build_graph(
    llm,
    collector=None,
    retriever=None,
    store=None,
):
    """노드 deps 를 주입해 컴파일된 ``GraphApp`` 를 반환한다.

    collector/retriever/store 미지정 시 그래프 자가완주용 fixture 를 사용한다(테스트·데모).
    실서비스 결선은 data/rag/store 의 get_*() 를 주입한다.
    """
    from langgraph.graph import END, START, StateGraph

    collector = collector or FixtureCollector()
    retriever = retriever or FixtureRetriever()
    nodes = Nodes(llm=llm, collector=collector, retriever=retriever, store=store)
    router = _Router(retriever)

    g = StateGraph(MacroLensState)
    g.add_node("safety_guardrail", nodes.safety_guardrail)
    g.add_node("intent_router", nodes.intent_router)
    g.add_node("trigger_calendar", nodes.trigger_calendar)
    g.add_node("data_collector", nodes.data_collector)
    g.add_node("sufficiency_check", nodes.sufficiency_check)
    g.add_node("rag_retriever", nodes.rag_retriever)
    g.add_node("transition_analyzer", nodes.transition_analyzer)
    g.add_node("sector_ranker", nodes.sector_ranker)
    g.add_node("coin_mapper", nodes.coin_mapper)
    g.add_node("change_detector", nodes.change_detector)
    g.add_node("scenario_analyzer", nodes.scenario_analyzer)
    g.add_node("briefing_synthesizer", nodes.briefing_synthesizer)

    g.add_edge(START, "safety_guardrail")
    g.add_conditional_edges(
        "safety_guardrail", route_safety, {"blocked": END, "ok": "intent_router"}
    )
    g.add_edge("intent_router", "trigger_calendar")
    g.add_edge("trigger_calendar", "data_collector")
    g.add_edge("data_collector", "sufficiency_check")
    g.add_edge("sufficiency_check", "rag_retriever")
    g.add_conditional_edges(
        "rag_retriever",
        router.route_retrieval,
        {
            "retry": "rag_retriever",
            "scenario": "scenario_analyzer",
            "insufficient": "briefing_synthesizer",
            "analyze": "transition_analyzer",
        },
    )
    g.add_edge("transition_analyzer", "sector_ranker")
    g.add_edge("sector_ranker", "coin_mapper")
    g.add_edge("coin_mapper", "change_detector")
    g.add_edge("change_detector", "briefing_synthesizer")
    g.add_edge("scenario_analyzer", "briefing_synthesizer")
    g.add_edge("briefing_synthesizer", END)

    compiled = g.compile()
    return GraphApp(compiled, nodes)


# --- GraphApp (stream 계약) -------------------------------------------------
def _merge(merged: dict, delta: dict) -> None:
    for k, v in delta.items():
        if k in _ACCUMULATORS and isinstance(v, list):
            merged.setdefault(k, [])
            merged[k] = list(merged[k]) + list(v)
        else:
            merged[k] = v


def _source_items(sources: list[Source]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for s in sources:
        ref = s.get("ref") or s.get("url") or s.get("title") or ""
        if ref in seen:
            continue
        seen.add(ref)
        out.append({"title": s.get("title", ""), "url": s.get("url", ""), "ref": s.get("ref", "")})
    return out


class GraphApp:
    """compiled LangGraph 를 감싸 SSE 이벤트 스트림으로 노출한다.

    최종 합성은 분석 그래프 완주(결정적 structured 노드) 후 ``llm.stream()`` 으로
    토큰을 **실시간** 산출하며(LLM v1.1), 스트림된 본문을 그대로 BriefingResult 로 확정·영속화한다
    (합성 LLM 단일 호출). stream 미지원 provider·근거부족·합성장애 경로는 노드가 만든 템플릿
    본문을 줄 단위로 청크한다(후방호환).
    """

    def __init__(self, compiled, nodes: Nodes) -> None:
        self._compiled = compiled
        self._nodes = nodes

    def stream(self, state_in: MacroLensState) -> Iterator[dict]:
        merged: dict = dict(state_in)
        try:
            for update in self._compiled.stream(state_in, stream_mode="updates"):
                for node_name, delta in update.items():
                    if not isinstance(delta, dict):
                        continue
                    _merge(merged, delta)
                    yield from self._events_for(node_name, delta, merged)
            yield self._done_event(merged)
        except AppError as e:  # pragma: no cover - 방어
            yield {"type": "error", "code": e.code, "user_message": e.user_message}
        except Exception:  # pragma: no cover - 방어
            logger.exception("graph stream failed")
            yield {
                "type": "error",
                "code": "INTERNAL",
                "user_message": "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            }

    # --- 노드 산출 → 이벤트 ---
    def _events_for(self, node: str, delta: dict, merged: dict) -> Iterator[dict]:
        if node == "safety_guardrail":
            yield {"type": "status", "stage": "analyze", "msg": "안전 점검"}
            if delta.get("blocked"):
                yield {"type": "token", "text": merged.get("safe_message", "")}
        elif node == "data_collector":
            yield {"type": "status", "stage": "collect", "msg": "거시 데이터 수집"}
        elif node == "rag_retriever":
            yield {"type": "status", "stage": "retrieve", "msg": "근거 검색"}
        elif node == "transition_analyzer":
            yield {"type": "section", "kind": "sector", "payload": {"transitions": delta.get("transitions", [])}}
        elif node == "sector_ranker":
            yield {"type": "section", "kind": "ranking", "payload": {"ranking": delta.get("sector_ranking", [])}}
        elif node == "coin_mapper":
            yield {"type": "section", "kind": "coin", "payload": {"coins": delta.get("coin_mapping", [])}}
        elif node == "change_detector":
            yield {"type": "section", "kind": "change", "payload": {"changes": delta.get("changes", [])}}
        elif node == "scenario_analyzer":
            yield {"type": "status", "stage": "analyze", "msg": "시나리오 분석"}
            sr = delta.get("scenario_result") or {}
            yield {"type": "section", "kind": "sector", "payload": {"scenario": sr}}
        elif node == "briefing_synthesizer":
            yield {"type": "status", "stage": "synthesize", "msg": "브리핑 합성"}
            briefing = delta.get("briefing") or {}
            yield from self._emit_briefing_tokens(briefing, merged)
            items = _source_items(merged.get("sources", []))
            if items:
                yield {"type": "sources", "items": items}

    # --- 브리핑 토큰 emit + 확정/영속화 (합성 LLM 단일 호출) ---
    def _emit_briefing_tokens(self, briefing: dict, merged: dict) -> Iterator[dict]:
        if briefing.get("_deferred"):
            # 정상 경로: 여기서 최초이자 유일하게 합성 LLM 을 스트림 호출한다.
            text, ok = "", False
            try:
                emitted: list[str] = []
                for delta_text in self._nodes.llm.stream(briefing_prompt(merged), temperature=0.2):
                    if not delta_text:
                        continue
                    emitted.append(delta_text)
                    yield {"type": "token", "text": delta_text}
                text = "".join(emitted)
                if text.strip():
                    # 면책 강제(AC-G2): 실시간 스트림에 누락되면 마지막 토큰으로 보강.
                    if prompts.DISCLAIMER not in text:
                        tail = f"\n\n{prompts.DISCLAIMER}"
                        text += tail
                        yield {"type": "token", "text": tail}
                    ok = True
            except Exception as e:  # 스트림 실패 → 장애 안내로 폴백(원인은 로그에 상세 기록)
                detail = getattr(e, "internal_detail", None) or f"{type(e).__name__}: {e}"
                logger.warning("live token stream failed; emitting failure notice — %s", detail)
            if not ok:
                text = prompts.SYNTH_FAILURE_BRIEFING.format(disclaimer=prompts.DISCLAIMER)
                for line in _chunk_text(text):
                    yield {"type": "token", "text": line}
            final = build_briefing(merged, text)
        else:
            # 근거부족·비스트리밍 provider: 노드가 만든 본문을 청크.
            body = briefing.get("body", "")
            for line in _chunk_text(body):
                yield {"type": "token", "text": line}
            final = {k: v for k, v in briefing.items() if k != "_deferred"}
        # 확정본을 merged 에 반영(done 요약용) + 영속화(전환 탐지 기준).
        merged["briefing"] = final
        self._nodes.persist_briefing(merged, final)

    def _done_event(self, merged: dict) -> dict:
        briefing = merged.get("briefing") or {}
        if merged.get("blocked"):
            summary = merged.get("safe_message", "")
        else:
            summary = briefing.get("conclusion", "")
        return {"type": "done", "thread_id": merged.get("thread_id", ""), "summary": summary}


def _chunk_text(text: str) -> list[str]:
    """본문을 토큰 스트리밍 흉내용 조각으로 분할(줄 단위, 개행 유지)."""
    if not text:
        return []
    parts = text.splitlines(keepends=True)
    return [p for p in parts if p]
