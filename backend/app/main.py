"""FastAPI 진입점. 레이어 결선·SSE·예외·lifespan.

lifespan: 결선 컨테이너 빌드 + RAG index_incremental() 1회(파일→ChromaDB).
표면: /api/v1/chat(SSE)·/health·/pins 만 노출(내부 그래프 비노출).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api.deps import container
from .api.routes import router
from .core.config import settings
from .core.exceptions import AppError
from .core.logging import configure_logging, get_logger
from .core.observability import configure_observability

configure_logging()
log = get_logger("macrolens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("MacroLens 시작 (provider=%s)", settings.llm_provider)
    container.build()
    container.index_rag()  # 파일→ChromaDB 증분 인덱싱(실패 시 degraded)
    yield
    log.info("MacroLens 종료")


app = FastAPI(title="MacroLens", version="0.1.0", lifespan=lifespan)
configure_observability(app)  # Logfire 계측(토큰/패키지 없으면 no-op)
app.include_router(router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """AppError → 표준 에러 본문(user_message만 노출, 내부 원인은 로그)."""
    trace_id = getattr(request.state, "trace_id", None)
    if exc.http_status >= 500:
        log.error("%s: %s", exc.code, exc.internal_detail)
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict(trace_id))


@app.get("/")
def root() -> dict:
    return {
        "service": "MacroLens",
        "version": "0.1.0",
        "health": "/api/v1/health",
        "chat": "/api/v1/chat",
        "docs": "/docs",
    }
