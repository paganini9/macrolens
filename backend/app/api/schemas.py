"""API 요청/응답 Pydantic 모델 (api_standard v1). 입력 검증 명시."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=2000)
    mode: Optional[Literal["briefing", "whatif", "deepdive"]] = None
    market_scope: Optional[list[Literal["KR", "US"]]] = None
    depth: Optional[Literal["conclusion", "evidence", "background"]] = None


class PinsBody(BaseModel):
    pinned_sectors: list[str] = Field(default_factory=list, max_length=20)


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    chroma: str
    db: str
