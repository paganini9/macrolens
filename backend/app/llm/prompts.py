"""노드별 프롬프트 빌더.

설계 원칙:
- 4요소(역할·맥락·지시·출력형식)를 모든 system 프롬프트에 포함.
- system 프롬프트에 ``[NODE:<tag>]`` 표지를 넣어 MockLLM(provider.py)이 결정적
  분기를 하도록 한다(테스트 재현성). 실제 provider 는 표지를 무시한다.
- 환각 0: 수치는 제공된 macro_data/근거에서만. LLM 은 해석·표현 담당.
- 안전: 추천·단정 금지, 면책·불확실성 강제(briefing/scenario).

각 빌더는 ``list[dict]`` (messages) 를 반환한다. structured 노드는 schemas.py 스키마와 함께
``LLM.generate(messages, schema=...)`` 로 호출한다.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.types import Evidence, Metric

# 합성 산출물에 항상 포함되어야 하는 면책 문구(AC-G2). 없으면 합성 실패로 간주.
DISCLAIMER = "본 자료는 투자 권유가 아니며 판단 재료를 제공합니다."

# 데이터/근거 부족 시 LLM 호출 없이 내보내는 결정적 안내(AC-A3, 단정 금지).
INSUFFICIENT_BRIEFING = (
    "[결론] 근거 부족 — 현재 확보된 거시 데이터·검색 근거가 부족해 단정적 판단을 내리기 어렵습니다.\n"
    "[주의] 일부 지표·근거가 결측되어 부분 정보만 제공합니다. 데이터가 보강되면 다시 점검해 주세요.\n"
    "\n{disclaimer}"
)

# 합성 LLM 장애 시 사용자에게 내보내는 안내(면책 포함, 재시도 유도).
SYNTH_FAILURE_BRIEFING = (
    "[안내] 브리핑 합성 중 일시적 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n"
    "\n{disclaimer}"
)

# 안전 가드레일이 차단 시 사용자에게 안내하는 제안형 메시지.
GUARDRAIL_SAFE_MESSAGE = (
    "MacroLens는 개별 종목 매매 신호나 투자 추천을 제공하지 않습니다. "
    "대신 거시 지표가 산업 섹터에 미치는 영향을 제안형으로 해석해 드립니다. "
    "예: '고금리 국면에서 어떤 섹터가 상대적으로 방어적인가?'"
)


def _fmt_metrics(macro_data: dict[str, Metric]) -> str:
    if not macro_data:
        return "(제공된 지표 없음)"
    lines = []
    for code, m in macro_data.items():
        lines.append(f"- {code}={m['value']}{m['unit']} (관측 {m['observed_at']}, 출처 {m['source']['title']})")
    return "\n".join(lines)


def _fmt_coin_prices(coin_prices: dict[str, Metric] | None) -> str:
    if not coin_prices:
        return "(코인 실시세 미수집 — 가격 인용 없이 방향만 서술)"
    lines = []
    for code, m in coin_prices.items():
        lines.append(f"- {code}={m['value']}{m['unit']} (관측 {m['observed_at']}, 출처 {m['source']['title']})")
    return "\n".join(lines)


def _fmt_evidence(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(검색 근거 없음)"
    lines = []
    for e in evidence:
        timing = f", 시차 {e['lead_lag']}/{e['lag_window']}" if e.get("lead_lag") else ""
        lines.append(f"- [{e['id']}|{e['type']}] {e['text']} (섹터 {e['sectors']}, 지표 {e['indicators']}{timing})")
    return "\n".join(lines)


def _sys(tag: str, role: str, context: str, instruction: str, fmt: str) -> dict:
    content = (
        f"[NODE:{tag}]\n"
        f"# 역할\n{role}\n\n"
        f"# 맥락\n{context}\n\n"
        f"# 지시\n{instruction}\n\n"
        f"# 출력 형식\n{fmt}"
    )
    return {"role": "system", "content": content}


# --- safety_guardrail ------------------------------------------------------
def safety_messages(user_input: str) -> list[dict]:
    sys = _sys(
        "safety_guardrail",
        "너는 MacroLens의 안전 가드레일이다. 그래프 진입점에서 입력 범위를 판정한다.",
        "MacroLens는 제안형 거시→섹터 해석 도구다. 개별 종목 매매 신호·투자 추천·수익 보장은 범위 밖이다.",
        "입력이 개별 종목 매수/매도 권유 요청이거나 수익 보장을 요구하면 block, "
        "거시·섹터·코인 해석 요청이면 allow 로 판정하라.",
        "JSON: {\"decision\":\"allow|block\",\"reason\":\"...\"}",
    )
    return [sys, {"role": "user", "content": user_input}]


# --- intent_router ---------------------------------------------------------
def intent_messages(user_input: str) -> list[dict]:
    sys = _sys(
        "intent_router",
        "너는 의도 분류기다.",
        "briefing=정기/일반 점검, whatif=가정 시나리오('만약/가정/유가 $100' 등), deepdive=특정 섹터 심층.",
        "사용자 입력의 의도를 셋 중 하나로 분류하라.",
        "JSON: {\"intent\":\"briefing|whatif|deepdive\"}",
    )
    return [sys, {"role": "user", "content": user_input}]


# --- transition_analyzer ---------------------------------------------------
def transition_messages(macro_data: dict[str, Metric], evidence: list[Evidence], sectors: list[str]) -> list[dict]:
    sys = _sys(
        "transition_analyzer",
        "너는 거시→섹터 전이 분석가다.",
        f"분석 대상 섹터: {sectors}\n\n# 지표\n{_fmt_metrics(macro_data)}\n\n# 근거\n{_fmt_evidence(evidence)}",
        "각 섹터에 대해 **지표→전달 메커니즘→섹터 영향**의 인과 체인을 명시적으로 밟아 "
        "방향(positive/negative/neutral)·강도(high/medium/low)·근거를 판정하라. "
        "rationale 에는 어떤 지표가 어떤 경로로 해당 섹터에 작용하는지 한 문장으로 적어라. "
        "반드시 위 근거 id 만 evidence_ids 로 인용하라(목록에 없는 id·수치 창작 금지). "
        "근거가 약하면 강도를 낮추고 uncertainty 에 한계를 솔직히 명시하라.",
        "JSON: {\"transitions\":[{\"sector\",\"direction\",\"strength\",\"rationale\",\"uncertainty\",\"evidence_ids\":[]}]}",
    )
    return [sys, {"role": "user", "content": "위 데이터·근거로 섹터 전이를 분석하라."}]


# --- sector_ranker ---------------------------------------------------------
def ranking_messages(transitions: list[dict[str, Any]], sectors: list[str]) -> list[dict]:
    sys = _sys(
        "sector_ranker",
        "너는 섹터 전이 수혜도 랭킹 분석가다.",
        f"유니버스: {sectors}\n전이 분석: {json.dumps(transitions, ensure_ascii=False)}",
        "전이 분석을 근거로 수혜도 점수(0~1)와 사유로 섹터를 랭킹하라. "
        "변별력이 없으면 빈 배열을 반환해 '뚜렷한 후보 없음'을 표시하라.",
        "JSON: {\"ranking\":[{\"sector\",\"score\",\"rationale\"}]}",
    )
    return [sys, {"role": "user", "content": "섹터를 랭킹하라."}]


# --- coin_mapper -----------------------------------------------------------
def coin_messages(
    macro_data: dict[str, Metric],
    evidence: list[Evidence],
    coin_prices: dict[str, Metric] | None = None,
) -> list[dict]:
    sys = _sys(
        "coin_mapper",
        "너는 거시→코인 영향 분석가다. 코인은 섹터와 **완전히 분리**해 다룬다(섹터 티커에 코인을 섞지 마라).",
        f"# 거시 지표\n{_fmt_metrics(macro_data)}\n\n# 코인 실시세\n{_fmt_coin_prices(coin_prices)}\n\n# 근거\n{_fmt_evidence(evidence)}",
        "위 코인 실시세를 기준으로, 거시 지표(금리·달러·유동성)가 각 코인에 미치는 영향을 "
        "지표→유동성/리스크선호→코인 인과 체인으로 방향·강도와 함께 판정하라. "
        "note 에는 위 실시세만 인용하고(가격 창작 금지), 근거 id 만 evidence_ids 로 인용하라.",
        "JSON: {\"coins\":[{\"ticker\",\"direction\",\"strength\",\"note\",\"evidence_ids\":[]}]}",
    )
    return [sys, {"role": "user", "content": "위 코인 실시세와 근거로 코인 영향을 분석하라."}]


# --- scenario_analyzer -----------------------------------------------------
def scenario_messages(user_input: str, evidence: list[Evidence]) -> list[dict]:
    sys = _sys(
        "scenario_analyzer",
        "너는 what-if 가정 분석가다.",
        f"# 근거(과거 유사 국면·인과)\n{_fmt_evidence(evidence)}",
        "사용자의 가정 시나리오에 대해 과거 유사 국면·인과 근거로 섹터/코인 영향 가설을 제시하라. "
        "확률적·가설적 표현을 쓰고 불확실성을 반드시 명시하라. 단정·추천 금지.",
        "JSON: {\"assumption\",\"impacts\":[{\"sector\",\"direction\",\"rationale\",\"probability\"}],\"uncertainty\"}",
    )
    return [sys, {"role": "user", "content": user_input}]


# --- briefing_synthesizer --------------------------------------------------
def briefing_messages(
    macro_data: dict[str, Metric],
    transitions: list[dict[str, Any]],
    ranking: list[dict[str, Any]],
    coins: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    depth: str,
    insufficient: bool = False,
    deepdive: bool = False,
    evidence: list[Evidence] | None = None,
) -> list[dict]:
    insufficient_note = (
        "\n\n# 중요\n데이터/근거가 부족하다. 단정 표현을 쓰지 말고 '근거 부족'을 명시하며 "
        "확인된 부분만 조심스럽게 요약하라."
        if insufficient
        else ""
    )
    # deepdive: 섹터별 심층(메커니즘·시차·근거 인용) + 검색 근거 상세를 추가 맥락으로 주입.
    deepdive_ctx = (
        f"\n# 심층 근거(deepdive)\n{_fmt_evidence(evidence or [])}"
        if deepdive
        else ""
    )
    deepdive_instr = (
        " 이번은 deepdive 요청이다. 상위 섹터 각각을 별도 문단으로 깊게 분석하라: "
        "전달 메커니즘·시차(lead/lag)·근거 id 를 명시하고 반례/리스크도 함께 짚어라."
        if deepdive
        else ""
    )
    sys = _sys(
        "briefing_synthesizer",
        "너는 최종 브리핑 합성가다. 제안형·중립 어조로 작성하며, 단정·종목 추천을 하지 않는다.",
        f"설명 깊이: {depth}\n# 지표\n{_fmt_metrics(macro_data)}\n"
        f"# 전이\n{json.dumps(transitions, ensure_ascii=False)}\n"
        f"# 랭킹\n{json.dumps(ranking, ensure_ascii=False)}\n"
        f"# 코인(분리)\n{json.dumps(coins, ensure_ascii=False)}\n"
        f"# 전환신호\n{json.dumps(changes, ensure_ascii=False)}{deepdive_ctx}{insufficient_note}",
        "다음 구획으로 한국어 브리핑을 작성하라: [결론] 한 줄, [근거] 지표→메커니즘→섹터, "
        "[주의] 워치포인트, [전환] 직전 대비 변화, [코인] 섹터와 분리한 영향. "
        "수치는 제공된 지표에서만 인용하라(창작 금지). 위 전이/랭킹/코인에 없는 섹터·코인을 새로 단정하지 마라."
        f"{deepdive_instr} "
        f"마지막 줄에 반드시 면책 문구를 포함하라: '{DISCLAIMER}'",
        "자유 텍스트(마크다운 허용). 면책 문구 누락 금지.",
    )
    return [sys, {"role": "user", "content": "위 분석을 종합해 브리핑을 작성하라."}]
