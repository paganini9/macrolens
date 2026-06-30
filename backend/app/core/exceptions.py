"""공통 예외 계층 (error_model v1). user_message 와 internal_detail 분리."""
from __future__ import annotations
from typing import Optional


class AppError(Exception):
    code: str = "INTERNAL"
    http_status: int = 500

    def __init__(self, user_message: str, internal_detail: Optional[str] = None):
        self.user_message = user_message
        self.internal_detail = internal_detail or user_message
        super().__init__(self.internal_detail)

    def to_dict(self, trace_id: Optional[str] = None) -> dict:
        return {"code": self.code, "user_message": self.user_message, "trace_id": trace_id}


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    http_status = 422


class DataSourceError(AppError):
    code = "DATA_SOURCE_ERROR"
    http_status = 502


class LLMError(AppError):
    code = "LLM_ERROR"
    http_status = 502


class RetrievalError(AppError):
    code = "RETRIEVAL_ERROR"
    http_status = 502


class GuardrailBlocked(AppError):
    code = "GUARDRAIL_BLOCKED"
    http_status = 200
