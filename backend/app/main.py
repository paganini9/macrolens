"""FastAPI 진입점 (Phase 0 스캐폴드). 05 백엔드 Agent 가 /chat·예외·router 로 확장.
lifespan 에서 03 RAG 의 index_incremental() 1회 호출 예정(파일→ChromaDB 동기화)."""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.config import settings
from .core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("macrolens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("MacroLens 시작 (provider=%s)", settings.llm_provider)
    # TODO(03/05): DB·Chroma 연결, RAG index_incremental() 1회(파일→ChromaDB)
    yield
    log.info("MacroLens 종료")


app = FastAPI(title="MacroLens", version="0.1.0", lifespan=lifespan)


@app.get("/")
def root() -> dict:
    return {
        "service": "MacroLens",
        "version": "0.1.0",
        "health": "/api/v1/health",
        "docs": "/docs",
    }


@app.get("/api/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "chroma": "pending",
        "db": "pending",
    }
