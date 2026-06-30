"""그래프 노드 12종.

각 노드는 ``MacroLensState`` 일부를 받아 **상태 델타(dict)** 를 반환한다.
deps(llm·collector·retriever·store)는 ``Nodes`` 인스턴스에 주입되고, build.py 가
메서드를 LangGraph 노드로 등록한다.

설계 불변식:
- 안전 가드레일은 진입점, 분기 노드는 temp=0 + structured output(재현성).
- 환각 0: 수치는 macro_data/근거에서만. data/근거 부족 시 '근거 부족' 분기(단정 금지).
- 코인은 섹터와 분리.
"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.types import Evidence, Metric, Source
from app.llm import prompts
from app.llm import schemas

from .state import (
    SECTOR_UNIVERSE,
    BriefingResult,
    MacroLensState,
)

logger = get_logger(__name__)

# 기본 수집 지표(MVP). 정규 브리핑이 거시 코어를 본다.
DEFAULT_INDICATORS = ["FFR", "DXY", "USDKRW", "US10Y"]

# 코인 코드(섹터와 분리). 그래프 로컬 정의 — app.data 를 import 하지 않아 트랙 결합 회피.
# 데이터 레이어가 동일 코드를 collect 지원하면 실시세가 macro_data[BTC/ETH] 로 흘러든다.
COIN_CODES = ["BTC", "ETH"]


def _target_sectors(state: MacroLensState) -> list[str]:
    """분석 대상 섹터 = 핀 우선, 없으면 유니버스."""
    pinned = state.get("pinned_sectors") or []
    return pinned if pinned else SECTOR_UNIVERSE


def _err(node: str, e: Exception) -> dict:
    code = e.code if isinstance(e, AppError) else "INTERNAL"
    detail = getattr(e, "internal_detail", None) or str(e)
    logger.warning("node %s error: %s", node, detail)
    return {"node": node, "code": code, "detail": detail}


class Nodes:
    def __init__(self, llm, collector, retriever, store) -> None:
        self.llm = llm
        self.collector = collector
        self.retriever = retriever
        self.store = store

    # --- 1. 안전 가드레일 (진입점) ---
    def safety_guardrail(self, state: MacroLensState) -> dict:
        try:
            res = self.llm.generate(
                prompts.safety_messages(state["user_input"]),
                schema=schemas.SAFETY_SCHEMA,
                temperature=0.0,
            )
            blocked = isinstance(res, dict) and res.get("decision") == "block"
        except AppError as e:
            # 가드레일 실패 시 보수적으로 통과시키되 오류 기록(데모 가용성).
            return {"blocked": False, "errors": [_err("safety_guardrail", e)]}
        if blocked:
            return {"blocked": True, "safe_message": prompts.GUARDRAIL_SAFE_MESSAGE}
        return {"blocked": False}

    # --- 2. 의도 라우터 ---
    def intent_router(self, state: MacroLensState) -> dict:
        if state.get("intent"):  # API 가 mode 로 명시하면 존중
            return {"intent": state["intent"]}
        try:
            res = self.llm.generate(
                prompts.intent_messages(state["user_input"]),
                schema=schemas.INTENT_SCHEMA,
                temperature=0.0,
            )
            intent = res.get("intent", "briefing") if isinstance(res, dict) else "briefing"
        except AppError as e:
            return {"intent": "briefing", "errors": [_err("intent_router", e)]}
        return {"intent": intent}

    # --- 3. 트리거 캘린더 ---
    def trigger_calendar(self, state: MacroLensState) -> dict:
        text = state.get("user_input", "")
        event_kw = ("FOMC", "CPI", "금리", "고용", "ECB", "한은", "발표")
        if any(k in text for k in event_kw):
            ttype = "event"
        elif "월말" in text or "정기" in text or "월간" in text:
            ttype = "month_end"
        else:
            ttype = "on_demand"
        return {"trigger_type": ttype}

    # --- 4. 데이터 수집 ---
    def data_collector(self, state: MacroLensState) -> dict:
        try:
            # 거시 코어 + 코인 시세를 함께 요청(코인은 섹터와 분리해 macro_data[BTC/ETH] 로 보관).
            # 데이터 레이어가 코인 코드를 지원하지 않으면 gap 으로 빠지므로 그래프는 그대로 완주한다.
            metrics: dict[str, Metric] = self.collector.collect(
                state.get("market_scope", ["KR"]), DEFAULT_INDICATORS + COIN_CODES
            )
            gaps = list(self.collector.gaps())
        except AppError as e:
            return {"macro_data": {}, "data_gaps": [], "errors": [_err("data_collector", e)]}
        sources: list[Source] = [m["source"] for m in metrics.values() if m.get("source")]
        return {"macro_data": metrics, "data_gaps": gaps, "sources": sources}

    # --- 5. 데이터 충분성 ---
    def sufficiency_check(self, state: MacroLensState) -> dict:
        data_ok = len(state.get("macro_data") or {}) > 0
        return {"data_sufficient": data_ok}

    # --- 6. RAG 검색 (루프 상한 N) ---
    def rag_retriever(self, state: MacroLensState) -> dict:
        sectors = _target_sectors(state)
        rnd = state.get("retrieval_round", 0) + 1
        try:
            hits: list[Evidence] = self.retriever.query(
                macro_state=state.get("macro_data", {}), sectors=sectors, k=6
            )
        except AppError as e:
            return {"rag_context": [], "retrieval_round": rnd, "errors": [_err("rag_retriever", e)]}
        sources: list[Source] = [h["source"] for h in hits if h.get("source")]
        return {"rag_context": hits, "retrieval_round": rnd, "sources": sources}

    # --- 7. 전이 분석 ---
    def transition_analyzer(self, state: MacroLensState) -> dict:
        try:
            res = self.llm.generate(
                prompts.transition_messages(
                    state.get("macro_data", {}), state.get("rag_context", []), _target_sectors(state)
                ),
                schema=schemas.TRANSITION_SCHEMA,
                temperature=0.0,
            )
            transitions = res.get("transitions", []) if isinstance(res, dict) else []
        except AppError as e:
            return {"transitions": [], "errors": [_err("transition_analyzer", e)]}
        return {"transitions": transitions}

    # --- 8. 섹터 랭킹 ---
    def sector_ranker(self, state: MacroLensState) -> dict:
        try:
            res = self.llm.generate(
                prompts.ranking_messages(state.get("transitions", []), _target_sectors(state)),
                schema=schemas.RANKING_SCHEMA,
                temperature=0.0,
            )
            ranking = res.get("ranking", []) if isinstance(res, dict) else []
        except AppError as e:
            return {"sector_ranking": [], "errors": [_err("sector_ranker", e)]}
        return {"sector_ranking": ranking}

    # --- 9. 코인 매핑 (섹터와 분리) ---
    def coin_mapper(self, state: MacroLensState) -> dict:
        macro = state.get("macro_data", {})
        # 수집된 코인 실시세만 추려 프롬프트에 실가격으로 주입(없으면 빈 dict → 일반 서술).
        coin_prices = {c: macro[c] for c in COIN_CODES if c in macro}
        try:
            res = self.llm.generate(
                prompts.coin_messages(macro, state.get("rag_context", []), coin_prices=coin_prices),
                schema=schemas.COIN_SCHEMA,
                temperature=0.0,
            )
            coins = res.get("coins", []) if isinstance(res, dict) else []
        except AppError as e:
            return {"coin_mapping": [], "errors": [_err("coin_mapper", e)]}
        return {"coin_mapping": coins}

    # --- 10. 전환 탐지 (직전 브리핑 대비) ---
    def change_detector(self, state: MacroLensState) -> dict:
        try:
            last = self.store.last_briefing() if self.store else None
        except AppError as e:
            return {"changes": [], "errors": [_err("change_detector", e)]}
        if not last:
            return {"changes": []}
        prev = {s.get("sector"): s for s in (last.get("sectors") or []) if isinstance(s, dict)}
        changes: list[dict[str, Any]] = []
        for t in state.get("transitions", []):
            sec = t.get("sector")
            p = prev.get(sec)
            if p and p.get("direction") != t.get("direction"):
                changes.append({"sector": sec, "note": f"전월 {p.get('direction')}→{t.get('direction')} 방향 전환"})
            elif p and p.get("strength") != t.get("strength"):
                changes.append({"sector": sec, "note": f"전월 대비 강도 변화({p.get('strength')}→{t.get('strength')})"})
        return {"changes": changes}

    # --- 11. 시나리오 분석 (what-if) ---
    def scenario_analyzer(self, state: MacroLensState) -> dict:
        try:
            res = self.llm.generate(
                prompts.scenario_messages(state["user_input"], state.get("rag_context", [])),
                schema=schemas.SCENARIO_SCHEMA,
                temperature=0.0,
            )
            scenario = res if isinstance(res, dict) else None
        except AppError as e:
            return {"scenario_result": None, "errors": [_err("scenario_analyzer", e)]}
        return {"scenario_result": scenario}

    # --- 12. 브리핑 합성 ---
    def briefing_synthesizer(self, state: MacroLensState) -> dict:
        insufficient = not state.get("data_sufficient", True) or not state.get("rag_context")
        # 데이터/근거 부족 시 LLM 호출 없이 결정적 '근거 부족' 안내(AC-A3, 단정 금지·환각 0).
        if insufficient:
            text = prompts.INSUFFICIENT_BRIEFING.format(disclaimer=prompts.DISCLAIMER)
            return self._finalize_briefing(state, text)
        # deepdive 의도면 섹터 심층(depth=background) + 근거 상세 주입(라우팅은 불변).
        deepdive = state.get("intent") == "deepdive"
        depth = "background" if deepdive else state.get("depth", "evidence")
        try:
            text = self.llm.generate(
                prompts.briefing_messages(
                    state.get("macro_data", {}),
                    state.get("transitions", []),
                    state.get("sector_ranking", []),
                    state.get("coin_mapping", []),
                    state.get("changes", []),
                    depth,
                    insufficient=insufficient,
                    deepdive=deepdive,
                    evidence=state.get("rag_context", []),
                ),
                temperature=0.2,
            )
            if isinstance(text, dict):  # 방어
                text = str(text)
        except AppError as e:
            # LLM 장애 시에도 사용자에게 면책 포함 안내를 제공(부분 결과 + 재시도 안내).
            note = _err("briefing_synthesizer", e)
            text = (
                "[안내] 브리핑 합성 중 일시적 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n"
                f"\n{prompts.DISCLAIMER}"
            )
            fallback: BriefingResult = {
                "thread_id": state["thread_id"],
                "conclusion": "일시적 오류로 브리핑을 완성하지 못했습니다.",
                "body": text,
                "sectors": state.get("transitions", []),
                "coins": state.get("coin_mapping", []),
                "changes": state.get("changes", []),
                "disclaimer": prompts.DISCLAIMER,
            }
            return {"briefing": fallback, "errors": [note]}
        return self._finalize_briefing(state, text)

    def _finalize_briefing(self, state: MacroLensState, text: str) -> dict:
        """면책 강제(AC-G2) + BriefingResult 구성 + 영속화(전환 탐지 기준)."""
        if prompts.DISCLAIMER not in text:
            text = f"{text.rstrip()}\n\n{prompts.DISCLAIMER}"
        briefing: BriefingResult = {
            "thread_id": state["thread_id"],
            "conclusion": _first_line(text),
            "body": text,
            "sectors": state.get("transitions", []),
            "coins": state.get("coin_mapping", []),
            "changes": state.get("changes", []),
            "disclaimer": prompts.DISCLAIMER,
        }
        if self.store:
            try:
                payload = dict(briefing)
                payload["trigger_type"] = state.get("trigger_type")
                self.store.save_briefing(state["thread_id"], payload)
            except AppError as e:
                return {"briefing": briefing, "errors": [_err("briefing_synthesizer.save", e)]}
        return {"briefing": briefing}


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        s = ln.strip().lstrip("#").strip()
        if s:
            # '[결론] ...' 형태면 라벨 제거
            if s.startswith("[") and "]" in s:
                s = s.split("]", 1)[1].strip()
            return s
    return text.strip()[:120]
