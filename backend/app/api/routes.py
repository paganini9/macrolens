"""API 라우터 — /chat(SSE)·/health·/pins. 내부 그래프 구조 비노출."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from app.core.config import settings
from app.core.logging import get_logger
from app.graph.state import initial_state
from app.llm.provider import available_providers, validate_provider

from .deps import container
from .schemas import ChatRequest, HealthResponse, PinsBody, ProviderValidateRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_status = "ok"
    try:
        container.store.get_pins()  # type: ignore[union-attr]
    except Exception:  # pragma: no cover
        db_status = "degraded"
    return HealthResponse(
        status="ok",
        llm_provider=settings.llm_provider,
        chroma=container.chroma_status,
        db=db_status,
    )


@router.get("/pins")
def get_pins() -> dict:
    return {"pinned_sectors": container.store.get_pins()}  # type: ignore[union-attr]


@router.put("/pins")
def put_pins(body: PinsBody) -> dict:
    container.store.set_pins(body.pinned_sectors)  # type: ignore[union-attr]
    return {"pinned_sectors": container.store.get_pins()}  # type: ignore[union-attr]


@router.get("/providers")
def get_providers() -> dict:
    """선택 가능한 LLM provider 목록(키 설정 여부·활성 표시). 키 값은 노출하지 않음."""
    return {
        "active": container.default_provider,
        "providers": available_providers(container.default_provider),
    }


@router.post("/providers/validate")
def post_validate_provider(body: ProviderValidateRequest) -> dict:
    """선택한 provider 의 API 키가 실제 동작하는지 최소 호출로 확인."""
    return validate_provider(body.provider)


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> EventSourceResponse:
    trace_id = uuid.uuid4().hex
    thread_id = req.thread_id or uuid.uuid4().hex
    pinned = container.store.get_pins()  # type: ignore[union-attr]
    graph = container.graph_for(req.provider)
    state = initial_state(
        thread_id=thread_id,
        user_input=req.message,
        market_scope=req.market_scope,
        pinned_sectors=pinned,
        depth=req.depth or "evidence",
        intent=req.mode,
    )

    def _gen():
        # 그래프(동기·LLM 블로킹)를 그대로 흘려보내고 SSE 프레임으로 변환.
        for event in graph.stream(state):
            etype = event.pop("type")
            if etype in ("done", "error"):
                event["trace_id"] = trace_id
            yield {"event": etype, "data": json.dumps(event, ensure_ascii=False)}

    async def _aiter():
        async for frame in iterate_in_threadpool(_gen()):
            if await request.is_disconnected():
                break
            yield frame

    return EventSourceResponse(_aiter())
