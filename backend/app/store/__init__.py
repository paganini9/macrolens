"""Store 레이어 (퍼시스턴스). 핀·브리핑 히스토리 영속화.

공개 API:
- Store     : interface_contracts v1 의 Protocol (타입 체크/의존성 주입용)
- SQLiteStore: SQLite 영속 구현
- get_store : 프로세스 전역 싱글톤 팩토리
- MockStore : 계약을 만족하는 인메모리 mock (다른 레이어/테스트용)
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.store.mocks import MockStore
from app.store.sqlite_store import SQLiteStore, StoreError, get_store


@runtime_checkable
class Store(Protocol):
    """interface_contracts v1 §3 — 핀·브리핑 히스토리 계약."""

    def get_pins(self) -> list[str]: ...
    def set_pins(self, sectors: list[str]) -> None: ...
    def save_briefing(self, thread_id: str, briefing: dict) -> str: ...
    def last_briefing(self) -> dict | None: ...
    def list_briefings(self, limit: int = 20) -> list[dict]: ...


__all__ = ["Store", "SQLiteStore", "MockStore", "StoreError", "get_store"]
