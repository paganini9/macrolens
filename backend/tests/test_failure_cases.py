"""실패 케이스 자동 검증 (수용기준 §4). 노드의 AppError graceful 처리.

- 데이터 소스 장애 → 부분 결과(근거 부족), 그래프 완주.
- RAG 검색 장애 → 근거 부족(단정 금지).
- 스토어 저장 장애 → 브리핑은 반환되고 오류는 errors 로 기록.
- 가드레일 LLM 장애 → 보수적 통과(데모 가용성).
면책은 모든 합성 경로에서 강제(AC-G2).
"""
from __future__ import annotations

from app.core.exceptions import DataSourceError, LLMError, RetrievalError
from app.graph.build import build_graph
from app.graph.fixtures import FixtureCollector, FixtureRetriever
from app.graph.state import initial_state
from app.llm.provider import MockLLM
from app.store import StoreError
from app.store.mocks import MockStore


def _events(app):
    st = initial_state(thread_id="t-fail", user_input="FOMC 발표 후 점검")
    return list(app.stream(st))


def _body(events):
    return "".join(e["text"] for e in events if e["type"] == "token")


class _RaisingCollector:
    def collect(self, market_scope, indicators):
        raise DataSourceError("외부 데이터 소스 장애")

    def gaps(self):
        return []


class _RaisingRetriever(FixtureRetriever):
    def query(self, macro_state, sectors, k=6, weights=None):
        raise RetrievalError("검색 백엔드 장애")


class _RaisingStore(MockStore):
    def save_briefing(self, thread_id, briefing):
        raise StoreError("DB 쓰기 실패")


def test_data_source_failure_degrades_to_insufficient():
    app = build_graph(llm=MockLLM(), collector=_RaisingCollector(), store=MockStore())
    events = _events(app)
    assert events[-1]["type"] == "done"
    body = _body(events)
    assert "근거 부족" in body
    assert "투자 권유가 아니" in body  # 면책 강제


def test_retrieval_failure_degrades_to_insufficient():
    app = build_graph(llm=MockLLM(), collector=FixtureCollector(), retriever=_RaisingRetriever(), store=MockStore())
    events = _events(app)
    assert events[-1]["type"] == "done"
    assert "근거 부족" in _body(events)


def test_store_failure_still_returns_briefing():
    app = build_graph(llm=MockLLM(), store=_RaisingStore())
    events = _events(app)
    # 저장 실패해도 사용자에겐 브리핑이 스트리밍되고 정상 종료
    assert events[-1]["type"] == "done"
    assert "투자 권유가 아니" in _body(events)
    assert any(e["type"] == "section" for e in events)


class _GuardrailFailLLM(MockLLM):
    def generate(self, messages, schema=None, temperature=0.2, max_tokens=1024):
        joined = "\n".join(m.get("content", "") for m in messages)
        if "[NODE:safety_guardrail]" in joined:
            raise LLMError("가드레일 LLM 장애", internal_detail="forced")
        return super().generate(messages, schema, temperature, max_tokens)


def test_guardrail_llm_failure_passes_conservatively():
    app = build_graph(llm=_GuardrailFailLLM(), store=MockStore())
    events = _events(app)
    # 가드레일 장애 시 차단하지 않고 진행(분석 섹션 등장) + 정상 종료
    assert events[-1]["type"] == "done"
    assert any(e["type"] == "section" for e in events)
