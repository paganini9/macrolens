"""LLM provider 추상화 (interface_contracts v1 §4).

`LLM` 계약: generate(messages, schema=None, temperature=0.2, max_tokens=1024)
  - schema 지정 시 structured output(dict), 없으면 자유 텍스트(str).

구현:
  - ClaudeProvider : anthropic SDK 사용. settings.anthropic_api_key 없으면 친절한 오류.
  - SolarProvider  : Upstage Solar 스텁(미구현 표시).
  - MockLLM        : 테스트용 결정적 출력(키워드/스키마 기반).
  - get_llm()      : settings.llm_provider 팩토리.
"""
from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

# 계약 기본값 (한 곳에서 관리)
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 1024
DEFAULT_MODEL_CLAUDE = "claude-3-5-sonnet-latest"
# Solar(Upstage) — OpenAI 호환 chat completions (참고_solar_upstage.md)
DEFAULT_MODEL_SOLAR = "solar-pro3"
SOLAR_BASE_URL = "https://api.upstage.ai/v1"


@runtime_checkable
class LLM(Protocol):
    """interface_contracts v1 §4. 04 제공, 노드들이 소비."""

    def generate(
        self,
        messages: list[dict],
        schema: dict | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict | str: ...


def _extract_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Anthropic Messages API는 system을 별도 파라미터로 받는다."""
    system_parts: list[str] = []
    chat: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        else:
            chat.append({"role": role, "content": content})
    system = "\n\n".join(system_parts) if system_parts else None
    return system, chat


def _schema_instruction(schema: dict) -> str:
    """structured output 강제용 지시문(프롬프트 주입)."""
    return (
        "반드시 아래 JSON 스키마에 맞는 **순수 JSON** 한 객체만 출력하라. "
        "코드펜스·설명·접두사를 붙이지 마라.\n"
        f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def _parse_json(text: str) -> dict:
    """모델 출력에서 JSON 추출(코드펜스/잡텍스트 방어)."""
    raw = text.strip()
    if raw.startswith("```"):
        # ```json ... ``` 제거
        raw = raw.split("```", 2)[1] if raw.count("```") >= 2 else raw.strip("`")
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    raw = raw.strip()
    # 첫 '{' ~ 마지막 '}' 슬라이스
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:  # pragma: no cover - 방어
        raise LLMError(
            "LLM 응답을 구조화된 형식으로 해석하지 못했습니다. 잠시 후 재시도해 주세요.",
            internal_detail=f"JSON parse fail: {e}; raw={text[:500]!r}",
        ) from e


class ClaudeProvider:
    """anthropic SDK 기반 기본 provider."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL_CLAUDE):
        self._api_key = api_key if api_key is not None else settings.anthropic_api_key
        self._model = model
        self._client = None  # lazy init

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMError(
                "Anthropic API 키가 설정되지 않았습니다. .env에 ANTHROPIC_API_KEY를 추가해 주세요.",
                internal_detail="settings.anthropic_api_key is empty",
            )
        try:
            import anthropic  # 지연 import (sandbox/테스트에서 미설치 허용)
        except ImportError as e:  # pragma: no cover
            raise LLMError(
                "anthropic SDK가 설치되지 않았습니다. `pip install anthropic`을 실행해 주세요.",
                internal_detail=str(e),
            ) from e
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def generate(
        self,
        messages: list[dict],
        schema: dict | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict | str:
        client = self._ensure_client()
        system, chat = _extract_system(messages)
        if schema is not None:
            instr = _schema_instruction(schema)
            system = f"{system}\n\n{instr}" if system else instr
        try:
            kwargs: dict = {
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": chat,
            }
            if system:
                kwargs["system"] = system
            resp = client.messages.create(**kwargs)
            text = "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            )
        except LLMError:
            raise
        except Exception as e:  # pragma: no cover - 네트워크/SDK 오류
            raise LLMError(
                "LLM 호출에 실패했습니다. 잠시 후 다시 시도해 주세요.",
                internal_detail=f"{type(e).__name__}: {e}",
            ) from e
        if schema is not None:
            return _parse_json(text)
        return text


class SolarProvider:
    """Upstage Solar provider (LLM_PROVIDER=solar). OpenAI 호환 chat completions.

    - base_url=https://api.upstage.ai/v1, model=solar-pro3, 키=settings.solar_api_key.
    - schema 지정 시: 프롬프트로 JSON 강제 + 후처리 파싱(Anthropic 경로와 동일 규약).
    - 재현성: 분기 노드는 temperature 낮게 호출(노드 측에서 0 지정).
    - client 주입 가능(테스트에서 네트워크 없이 검증).
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL_SOLAR, client=None):
        self._api_key = api_key if api_key is not None else settings.solar_api_key
        self._model = model
        self._client = client  # 주입 시 lazy init 생략

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMError(
                "Solar API 키가 설정되지 않았습니다. .env에 SOLAR_API_KEY를 추가해 주세요.",
                internal_detail="settings.solar_api_key is empty",
            )
        try:
            from openai import OpenAI  # 지연 import
        except ImportError as e:  # pragma: no cover
            raise LLMError(
                "openai SDK가 설치되지 않았습니다. `pip install openai`를 실행해 주세요.",
                internal_detail=str(e),
            ) from e
        self._client = OpenAI(api_key=self._api_key, base_url=SOLAR_BASE_URL)
        return self._client

    def generate(
        self,
        messages: list[dict],
        schema: dict | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict | str:
        client = self._ensure_client()
        chat = list(messages)
        if schema is not None:
            # OpenAI 호환: system 역할로 JSON 강제 지시 주입(Anthropic 경로와 동일 후처리).
            chat = chat + [{"role": "system", "content": _schema_instruction(schema)}]
        try:
            resp = client.chat.completions.create(
                model=self._model,
                messages=chat,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            text = resp.choices[0].message.content or ""
        except LLMError:
            raise
        except Exception as e:  # pragma: no cover - 네트워크/SDK 오류
            raise LLMError(
                "LLM 호출에 실패했습니다. 잠시 후 다시 시도해 주세요.",
                internal_detail=f"{type(e).__name__}: {e}",
            ) from e
        if schema is not None:
            return _parse_json(text)
        return text


class MockLLM:
    """테스트용 결정적 LLM.

    스키마/메시지 키워드를 보고 고정적이고 재현 가능한 출력을 만든다.
    네트워크·API 키 불필요. test_graph E2E·라우팅 단위 테스트에서 사용.
    """

    SECTOR_UNIVERSE = [
        "AI/SW",
        "반도체",
        "2차전지",
        "자동차",
        "금융",
        "에너지/화학",
        "바이오/헬스케어",
        "인터넷/플랫폼",
    ]

    def __init__(self, overrides: dict | None = None):
        # 특정 node_tag → 반환값을 강제 주입하고 싶을 때 사용.
        self._overrides = overrides or {}

    def generate(
        self,
        messages: list[dict],
        schema: dict | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict | str:
        # [NODE:xxx] 표지는 system 프롬프트에 있으므로 전체에서 탐지하되,
        # 키워드 분기(차단/의도)는 **사용자 메시지**로만 판정한다.
        # (system 지시문이 차단 키워드를 서술하므로 전체를 보면 오탐된다.)
        joined = "\n".join(m.get("content", "") for m in messages)
        user_text = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )
        tag = self._detect_tag(joined, schema)
        if tag in self._overrides:
            return self._overrides[tag]
        handler = getattr(self, f"_gen_{tag}", None)
        if handler is not None:
            return handler(user_text)
        # 스키마 없으면 자유 텍스트, 있으면 빈 dict 방어
        return {} if schema is not None else "MOCK_RESPONSE"

    # --- tag 판별 (프롬프트 내 식별 표지 또는 키워드) ---
    @staticmethod
    def _detect_tag(text: str, schema: dict | None) -> str:
        # prompts.py 가 system 프롬프트에 [NODE:xxx] 표지를 넣는다.
        for tag in (
            "safety_guardrail",
            "intent_router",
            "transition_analyzer",
            "sector_ranker",
            "coin_mapper",
            "scenario_analyzer",
            "briefing_synthesizer",
        ):
            if f"[NODE:{tag}]" in text:
                return tag
        return "free"

    # --- 노드별 결정적 출력 ---
    def _gen_safety_guardrail(self, text: str) -> dict:
        # 개별종목 매매 신호/추천/수익보장 요청만 차단(기본 allow). text=사용자 메시지.
        block_kw = [
            "사도 될까", "사도 돼", "사야 할까", "사야 돼", "팔까", "팔아야",
            "매수", "매도", "사라고", "꼭 사", "추천 종목", "보장", "100% 수익",
        ]
        blocked = any(k in text for k in block_kw)
        return {
            "decision": "block" if blocked else "allow",
            "reason": "투자 추천 요청으로 판단" if blocked else "범위 내 질의",
        }

    def _gen_intent_router(self, text: str) -> dict:
        if "what" in text.lower() or "if" in text.lower() or "가정" in text or "만약" in text:
            return {"intent": "whatif"}
        if "딥다이브" in text or "deepdive" in text.lower() or "자세히" in text:
            return {"intent": "deepdive"}
        return {"intent": "briefing"}

    def _gen_transition_analyzer(self, text: str) -> dict:
        return {
            "transitions": [
                {
                    "sector": "반도체",
                    "direction": "negative",
                    "strength": "high",
                    "rationale": "고금리·강달러가 메모리 다운사이클과 겹쳐 밸류에이션 압박",
                    "uncertainty": "medium",
                    "evidence_ids": ["causal-0001", "causal-0003"],
                },
                {
                    "sector": "AI/SW",
                    "direction": "neutral",
                    "strength": "medium",
                    "rationale": "수요 견조하나 금리 부담으로 상대 방어",
                    "uncertainty": "medium",
                    "evidence_ids": ["causal-0001"],
                },
            ]
        }

    def _gen_sector_ranker(self, text: str) -> dict:
        return {
            "ranking": [
                {"sector": "AI/SW", "score": 0.62, "rationale": "상대 방어 우위"},
                {"sector": "반도체", "score": 0.31, "rationale": "사이클·금리 동반 부담"},
            ]
        }

    def _gen_coin_mapper(self, text: str) -> dict:
        return {
            "coins": [
                {
                    "ticker": "BTC",
                    "direction": "negative",
                    "strength": "medium",
                    "note": "강달러·고금리 유동성 위축",
                    "evidence_ids": ["causal-0002"],
                }
            ]
        }

    def _gen_scenario_analyzer(self, text: str) -> dict:
        return {
            "assumption": "가정 시나리오",
            "impacts": [
                {
                    "sector": "반도체",
                    "direction": "negative",
                    "rationale": "과거 유사 국면에서 약세",
                    "probability": "likely",
                }
            ],
            "uncertainty": "과거 사례 기반 추정으로 불확실성 존재",
        }

    def _gen_briefing_synthesizer(self, text: str) -> str:
        return (
            "[결론] 강달러·고금리 지속으로 한국 수출 섹터는 단기 부담, AI/SW는 상대 방어.\n"
            "[근거] 금리 상승은 반도체 밸류에이션을 압박(causal-0001), 강달러는 수출주에 양면적(causal-0003).\n"
            "[주의] 메모리 사이클 반등 시점이 변수.\n"
            "[전환] 전월 대비 반도체 약세 강화.\n"
            "[코인] BTC는 섹터와 분리해 보면 유동성 위축에 약세 편향.\n"
            "본 자료는 투자 권유가 아니며 판단 재료를 제공합니다."
        )


def get_llm(provider: str | None = None) -> LLM:
    """settings.llm_provider 기반 팩토리. provider 인자로 강제 override 가능."""
    name = (provider or settings.llm_provider or "claude").lower()
    if name == "claude":
        return ClaudeProvider()
    if name == "solar":
        return SolarProvider()
    if name == "mock":
        return MockLLM()
    raise LLMError(
        f"알 수 없는 LLM provider: {name}. claude|solar|mock 중 하나여야 합니다.",
        internal_detail=f"unknown provider {name!r}",
    )
