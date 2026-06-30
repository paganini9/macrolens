"""LLM provider 테스트 — MockLLM 분기 범위 + SolarProvider 매핑(주입 client, 오프라인)."""
from __future__ import annotations

import pytest

from app.core.exceptions import LLMError
from app.llm import schemas
from app.llm.provider import MockLLM, SolarProvider, get_llm


# --- MockLLM: 키워드 분기는 사용자 메시지로만 판정(system 지시문 오탐 방지) ---
def test_mock_safety_uses_user_message_not_system():
    llm = MockLLM()
    msgs = [
        {"role": "system", "content": "[NODE:safety_guardrail] 수익 보장을 요구하면 block 하라."},
        {"role": "user", "content": "FOMC 후 섹터 점검"},
    ]
    out = llm.generate(msgs, schema=schemas.SAFETY_SCHEMA, temperature=0.0)
    assert out["decision"] == "allow"  # system 의 '보장' 키워드에 오탐되지 않음


def test_mock_safety_blocks_trade_question():
    llm = MockLLM()
    msgs = [
        {"role": "system", "content": "[NODE:safety_guardrail]"},
        {"role": "user", "content": "삼성전자 지금 사도 될까?"},
    ]
    assert llm.generate(msgs, schema=schemas.SAFETY_SCHEMA)["decision"] == "block"


# --- SolarProvider: OpenAI 호환 호출 매핑(주입 client) ---
class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResp(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def test_solar_free_text():
    client = _FakeClient("강달러·고금리 요약")
    llm = SolarProvider(client=client)
    out = llm.generate([{"role": "user", "content": "요약"}], temperature=0.0)
    assert out == "강달러·고금리 요약"
    assert client.chat.completions.last_kwargs["model"] == "solar-pro3"
    assert client.chat.completions.last_kwargs["stream"] is False


def test_solar_structured_parses_json():
    client = _FakeClient('{"intent":"whatif"}')
    llm = SolarProvider(client=client)
    out = llm.generate(
        [{"role": "user", "content": "만약 유가 $100"}],
        schema=schemas.INTENT_SCHEMA,
        temperature=0.0,
    )
    assert out == {"intent": "whatif"}


def test_solar_missing_key_raises_friendly():
    llm = SolarProvider(api_key="")
    with pytest.raises(LLMError):
        llm.generate([{"role": "user", "content": "x"}])


def test_get_llm_factory():
    assert isinstance(get_llm("mock"), MockLLM)
    assert isinstance(get_llm("solar"), SolarProvider)
    with pytest.raises(LLMError):
        get_llm("unknown")
