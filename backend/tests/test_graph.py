"""그래프 E2E·라우팅 테스트 (T-40 DoD).

MockLLM + mock data/rag/store 로 결정적 완주를 검증한다.
- SC-A 브리핑 완주(이벤트 순서·섹션·출처·면책).
- AC-G1 가드레일 차단.
- SC-C what-if 분기.
- '근거 부족' 분기(단정 금지).
- 재현성(같은 입력 → 같은 경로).
- 검색 루프 종료 보장.
"""
from __future__ import annotations

from collections import Counter


from app.graph.build import build_graph
from app.graph.state import MAX_RETRIEVAL_ROUNDS, initial_state
from app.llm.provider import MockLLM
from app.store.mocks import MockStore


def _run(user_input: str, **kw):
    app = build_graph(llm=MockLLM(), store=MockStore())
    st = initial_state(thread_id="t-test", user_input=user_input, **kw)
    return list(app.stream(st))


def _body(events) -> str:
    return "".join(e["text"] for e in events if e["type"] == "token")


# --- SC-A 정기 브리핑 -------------------------------------------------------
def test_briefing_e2e_emits_full_stream():
    events = _run("FOMC 발표 후 한국 섹터 점검", market_scope=["KR"])
    kinds = Counter(e["type"] for e in events)
    assert kinds["status"] >= 3
    assert kinds["done"] == 1

    stages = [e["stage"] for e in events if e["type"] == "status"]
    assert {"collect", "retrieve", "synthesize"} <= set(stages)

    sections = [e["kind"] for e in events if e["type"] == "section"]
    assert set(sections) == {"sector", "ranking", "coin", "change"}

    # AC-G2 면책 강제
    assert "투자 권유가 아니" in _body(events)
    # 출처 부착(AC-A2)
    assert any(e["type"] == "sources" and e["items"] for e in events)
    # done 은 마지막, 결론 요약 포함
    assert events[-1]["type"] == "done"
    assert events[-1]["summary"]


def test_event_order_status_then_sections_then_done():
    events = _run("FOMC 발표 후 한국 섹터 점검")
    types = [e["type"] for e in events]
    assert types[0] == "status"          # 진입(안전 점검)
    assert types[-1] == "done"
    # done 이전에 error 없음(정상 경로)
    assert "error" not in types


# --- AC-G1 가드레일 ---------------------------------------------------------
def test_guardrail_blocks_individual_stock_question():
    events = _run("삼성전자 지금 사도 될까?")
    # 분석 섹션이 전혀 나오지 않고, 안전 안내 + done 으로 종료
    assert not any(e["type"] == "section" for e in events)
    body = _body(events)
    assert "추천" in body or "제안형" in body
    assert events[-1]["type"] == "done"


# --- SC-C what-if -----------------------------------------------------------
def test_whatif_routes_to_scenario():
    events = _run("만약 유가가 $100가 되면 어떤 섹터가 영향을 받을까?")
    # 시나리오 섹션이 emit 되고, 전이/랭킹 분석 경로는 타지 않는다(배타성)
    section_kinds = [e["kind"] for e in events if e["type"] == "section"]
    payloads = [e["payload"] for e in events if e["type"] == "section"]
    assert any("scenario" in p for p in payloads)
    assert "ranking" not in section_kinds
    assert "투자 권유가 아니" in _body(events)


# --- '근거 부족' 분기 -------------------------------------------------------
class _EmptyCollector:
    def collect(self, market_scope, indicators):
        return {}

    def gaps(self):
        return []


class _EmptyRetriever:
    def query(self, macro_state, sectors, k=6, weights=None):
        return []

    def is_sufficient(self, hits, sectors):
        return False

    def index_incremental(self):
        return 0

    def ensure_synced(self):
        return None


def test_insufficient_data_branch_no_assertion():
    app = build_graph(
        llm=MockLLM(), collector=_EmptyCollector(), retriever=_EmptyRetriever(), store=MockStore()
    )
    st = initial_state(thread_id="t-empty", user_input="FOMC 발표 후 점검")
    events = list(app.stream(st))
    # 분석 섹션 없이 합성으로 직행, 면책 포함, 정상 종료
    assert events[-1]["type"] == "done"
    assert "투자 권유가 아니" in _body(events)
    # 전이/랭킹/코인 분석 섹션을 타지 않음
    assert not any(e.get("kind") in ("ranking", "coin") for e in events if e["type"] == "section")


def test_retrieval_loop_terminates():
    # is_sufficient 가 항상 False 여도 루프는 상한 N 에서 강제 전진(종료 보장)
    app = build_graph(
        llm=MockLLM(), retriever=_EmptyRetriever(), store=MockStore()
    )
    st = initial_state(thread_id="t-loop", user_input="FOMC 발표 후 점검")
    events = list(app.stream(st))
    assert events[-1]["type"] == "done"
    retrieve_count = sum(1 for e in events if e["type"] == "status" and e["stage"] == "retrieve")
    assert retrieve_count <= MAX_RETRIEVAL_ROUNDS


# --- LLM 장애 graceful degradation -----------------------------------------
class _FailingSynthLLM(MockLLM):
    """briefing 합성만 실패시켜 폴백 경로를 검증."""

    def generate(self, messages, schema=None, temperature=0.2, max_tokens=1024):
        from app.core.exceptions import LLMError

        joined = "\n".join(m.get("content", "") for m in messages)
        if "[NODE:briefing_synthesizer]" in joined:
            raise LLMError("일시적 오류", internal_detail="forced")
        return super().generate(messages, schema, temperature, max_tokens)


def test_briefing_llm_failure_yields_disclaimer_fallback():
    app = build_graph(llm=_FailingSynthLLM(), store=MockStore())
    st = initial_state(thread_id="t-fail", user_input="FOMC 발표 후 점검")
    events = list(app.stream(st))
    # 합성 실패에도 면책 포함 안내 + 정상 종료(스트림이 조용히 끝나지 않음)
    assert events[-1]["type"] == "done"
    body = _body(events)
    assert "투자 권유가 아니" in body
    assert "다시 시도" in body


# --- 재현성 -----------------------------------------------------------------
def test_determinism_same_input_same_path():
    a = _run("FOMC 발표 후 한국 섹터 점검")
    b = _run("FOMC 발표 후 한국 섹터 점검")
    sig_a = [(e["type"], e.get("stage"), e.get("kind")) for e in a]
    sig_b = [(e["type"], e.get("stage"), e.get("kind")) for e in b]
    assert sig_a == sig_b


# --- 실시간 토큰 스트리밍 (LLM v1.1) ----------------------------------------
def test_streaming_emits_multiple_live_token_events():
    events = _run("FOMC 발표 후 한국 섹터 점검")
    tokens = [e for e in events if e["type"] == "token"]
    # 줄 단위 1~5조각이 아니라 ~12자 델타 다수(실 토큰 스트리밍 입증).
    assert len(tokens) > 5
    body = _body(events)
    assert "[결론]" in body
    assert "투자 권유가 아니" in body  # 면책 강제(AC-G2)


def test_streaming_event_order_sections_then_tokens_then_sources_then_done():
    events = _run("FOMC 발표 후 한국 섹터 점검")
    types = [e["type"] for e in events]
    last_section = max(i for i, t in enumerate(types) if t == "section")
    first_token = min(i for i, t in enumerate(types) if t == "token")
    last_token = max(i for i, t in enumerate(types) if t == "token")
    sources_idx = max(i for i, t in enumerate(types) if t == "sources")
    # status* → section* → token* → sources → done
    assert last_section < first_token
    assert last_token < sources_idx
    assert types[-1] == "done"


def test_streaming_token_sequence_is_deterministic():
    a = [e["text"] for e in _run("FOMC 발표 후 한국 섹터 점검") if e["type"] == "token"]
    b = [e["text"] for e in _run("FOMC 발표 후 한국 섹터 점검") if e["type"] == "token"]
    assert a == b and len(a) > 1


# --- deepdive 라우팅 (3원칙 보존: 완전성·배타성·종료) ------------------------
def test_deepdive_routes_through_full_analysis():
    events = _run("반도체 섹터를 자세히 딥다이브 해줘", intent="deepdive")
    section_kinds = {e["kind"] for e in events if e["type"] == "section"}
    # whatif 와 달리 전체 분석 경로(전이·랭킹·코인·전환)를 그대로 탄다(라우팅 불변).
    assert {"sector", "ranking", "coin", "change"} <= section_kinds
    assert events[-1]["type"] == "done"
    assert "투자 권유가 아니" in _body(events)
