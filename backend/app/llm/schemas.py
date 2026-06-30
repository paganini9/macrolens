"""노드별 structured output JSON 스키마.

분기/추출 노드는 ``LLM.generate(messages, schema=...)`` 로 결정적 dict 를 받는다.
스키마는 graph/state.py 의 산출 타입과 1:1 정합한다(재현성·검증).
"""
from __future__ import annotations

_DIRECTION = {"type": "string", "enum": ["positive", "negative", "neutral"]}
_STRENGTH = {"type": "string", "enum": ["high", "medium", "low"]}

SAFETY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["allow", "block"]},
        "reason": {"type": "string"},
    },
    "required": ["decision", "reason"],
}

INTENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["briefing", "whatif", "deepdive"]},
    },
    "required": ["intent"],
}

TRANSITION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "transitions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string"},
                    "direction": _DIRECTION,
                    "strength": _STRENGTH,
                    "rationale": {"type": "string"},
                    "uncertainty": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["sector", "direction", "strength", "rationale", "evidence_ids"],
            },
        }
    },
    "required": ["transitions"],
}

RANKING_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string"},
                    "score": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["sector", "score", "rationale"],
            },
        }
    },
    "required": ["ranking"],
}

COIN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "coins": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "direction": _DIRECTION,
                    "strength": _STRENGTH,
                    "note": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ticker", "direction", "note"],
            },
        }
    },
    "required": ["coins"],
}

SCENARIO_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "assumption": {"type": "string"},
        "impacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string"},
                    "direction": _DIRECTION,
                    "rationale": {"type": "string"},
                    "probability": {"type": "string"},
                },
                "required": ["sector", "direction", "rationale", "probability"],
            },
        },
        "uncertainty": {"type": "string"},
    },
    "required": ["assumption", "impacts", "uncertainty"],
}
