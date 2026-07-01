"""API 표면 테스트 (T-50 / G2). /health·/pins·/chat(SSE) 계약 검증.

container 를 mock 으로 결선해 오프라인·결정적으로 실행한다(Chroma 인덱싱·API 키 불필요).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.graph.build import build_graph
from app.llm.provider import MockLLM
from app.store.mocks import MockStore


@pytest.fixture()
def client(monkeypatch):
    store = MockStore()

    def _build():
        deps.container.store = store
        deps.container.collector = None   # build_graph → FixtureCollector
        deps.container.retriever = None   # build_graph → FixtureRetriever
        deps.container.llm = MockLLM()
        deps.container.chroma_status = "ok"
        deps.container.default_provider = "solar"
        deps.container._graphs = {}
        deps.container.graph = build_graph(llm=MockLLM(), store=store)

    monkeypatch.setattr(deps.container, "build", _build)
    monkeypatch.setattr(deps.container, "index_rag", lambda: None)

    from app.main import app

    with TestClient(app) as c:
        yield c


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    etype = None
    for line in text.splitlines():
        if line.startswith("event:"):
            etype = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = line.split(":", 1)[1].strip()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"raw": payload}
            events.append((etype or "", data))
    return events


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["chroma"] == "ok"
    assert body["db"] == "ok"


def test_pins_round_trip(client):
    # 시드 핀 존재
    r = client.get("/api/v1/pins")
    assert r.status_code == 200
    assert isinstance(r.json()["pinned_sectors"], list)
    # 변경 반영
    r = client.put("/api/v1/pins", json={"pinned_sectors": ["반도체", "AI/SW"]})
    assert r.status_code == 200
    assert r.json()["pinned_sectors"] == ["반도체", "AI/SW"]
    assert client.get("/api/v1/pins").json()["pinned_sectors"] == ["반도체", "AI/SW"]


def test_chat_validation_rejects_empty_message(client):
    r = client.post("/api/v1/chat", json={"message": ""})
    assert r.status_code == 422


def test_chat_sse_full_stream(client):
    r = client.post(
        "/api/v1/chat",
        json={"message": "FOMC 발표 후 한국 섹터 점검", "market_scope": ["KR"]},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    events = _parse_sse(r.text)
    types = [t for t, _ in events]
    assert "status" in types
    assert "section" in types
    assert "sources" in types
    assert types[-1] == "done"
    # done 에 trace_id·thread_id
    done = events[-1][1]
    assert done["trace_id"] and done["thread_id"]
    # 면책(token 본문)
    body = "".join(d.get("text", "") for t, d in events if t == "token")
    assert "투자 권유가 아니" in body


def test_chat_guardrail_block(client):
    r = client.post("/api/v1/chat", json={"message": "삼성전자 지금 사도 될까?"})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    # 분석 섹션 없이 안전 안내 후 done
    assert not any(t == "section" for t, _ in events)
    assert events[-1][0] == "done"


def test_providers_list(client):
    r = client.get("/api/v1/providers")
    assert r.status_code == 200
    body = r.json()
    names = [p["name"] for p in body["providers"]]
    assert set(names) == {"solar", "claude", "mock"}
    # mock 은 항상 configured=True
    assert next(p for p in body["providers"] if p["name"] == "mock")["configured"] is True
    assert body["active"]


def test_provider_validate_mock_ok(client):
    # mock 은 네트워크 없이 항상 ok
    r = client.post("/api/v1/providers/validate", json={"provider": "mock"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock" and body["ok"] is True


def test_provider_validate_rejects_unknown(client):
    r = client.post("/api/v1/providers/validate", json={"provider": "gpt"})
    assert r.status_code == 422  # Literal 검증


def test_chat_with_mock_provider_override(client):
    # provider=mock 명시 → 정상 스트림(기본 provider와 무관하게 동작)
    r = client.post("/api/v1/chat", json={"message": "FOMC 발표 후 점검", "provider": "mock"})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    assert events[-1][0] == "done"
