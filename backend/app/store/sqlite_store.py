"""SQLite 기반 Store 구현 (interface_contracts v1).

핀(관심 섹터)·브리핑 히스토리를 단일 SQLite 파일에 영속화한다.
- 재시작 후에도 핀·히스토리가 살아남아야 한다(전환 탐지 = last_briefing 의존).
- FastAPI는 스레드 풀에서 핸들러를 실행하므로 단일 커넥션 +
  쓰기 직렬화용 Lock 으로 동시성 안전을 확보한다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


class StoreError(AppError):
    """퍼시스턴스 계층 오류. AppError(INTERNAL) 의 최소 확장."""

    code = "INTERNAL"
    http_status = 500


def _utc_now_iso() -> str:
    """created_at 정렬·전환 탐지를 위한 ISO-8601 UTC 타임스탬프."""
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    """Store Protocol 의 SQLite 구현.

    스키마(없으면 생성):
      briefings(id, thread_id, created_at, payload_json, trigger_type)  # created_at 인덱스
      pins(sector PRIMARY KEY, ord)                                      # ord = 표시 순서
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or settings.sqlite_path
        # 부모 디렉터리 보장(상대경로 './macrolens.db' 면 cwd 기준).
        path = Path(self._db_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        # 스레드 풀에서 공유하는 단일 커넥션. 쓰기는 _lock 으로 직렬화.
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()
        logger.info("SQLiteStore initialized at %s", self._db_path)

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS briefings (
                    id           TEXT PRIMARY KEY,
                    thread_id    TEXT,
                    created_at   TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    trigger_type TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_briefings_created_at
                    ON briefings (created_at DESC);
                CREATE TABLE IF NOT EXISTS pins (
                    sector TEXT PRIMARY KEY,
                    ord    INTEGER NOT NULL
                );
                """
            )
            self._conn.commit()

    # ── 핀(관심 섹터) ────────────────────────────────────────────────
    def get_pins(self) -> list[str]:
        """표시 순서(ord) 오름차순으로 섹터 목록 반환."""
        cur = self._conn.execute("SELECT sector FROM pins ORDER BY ord ASC")
        return [row["sector"] for row in cur.fetchall()]

    def set_pins(self, sectors: list[str]) -> None:
        """핀 전체를 원자적으로 교체. 주어진 순서를 ord 0,1,2… 로 보존."""
        rows = [(sector, idx) for idx, sector in enumerate(sectors)]
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                self._conn.execute("DELETE FROM pins")
                if rows:
                    self._conn.executemany(
                        "INSERT INTO pins (sector, ord) VALUES (?, ?)", rows
                    )
                self._conn.commit()
            except sqlite3.Error as exc:  # pragma: no cover - 방어적
                self._conn.rollback()
                raise StoreError("핀 저장 중 오류가 발생했습니다.", str(exc)) from exc

    # ── 브리핑 히스토리 ──────────────────────────────────────────────
    def save_briefing(self, thread_id: str, briefing: dict) -> str:
        """브리핑을 저장하고 생성된 id(uuid4 hex)를 반환."""
        bid = uuid.uuid4().hex
        created_at = _utc_now_iso()
        payload_json = json.dumps(briefing, ensure_ascii=False)
        trigger_type = briefing.get("trigger_type")
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO briefings "
                    "(id, thread_id, created_at, payload_json, trigger_type) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (bid, thread_id, created_at, payload_json, trigger_type),
                )
                self._conn.commit()
            except sqlite3.Error as exc:  # pragma: no cover - 방어적
                self._conn.rollback()
                raise StoreError("브리핑 저장 중 오류가 발생했습니다.", str(exc)) from exc
        return bid

    def last_briefing(self) -> dict | None:
        """가장 최근 브리핑 payload 반환(전환 탐지용). 없으면 None."""
        cur = self._conn.execute(
            "SELECT payload_json FROM briefings "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
        )
        row = cur.fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_briefings(self, limit: int = 20) -> list[dict]:
        """최신순 브리핑 payload 목록(limit 적용)."""
        cur = self._conn.execute(
            "SELECT payload_json FROM briefings "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return [json.loads(row["payload_json"]) for row in cur.fetchall()]


# ── 프로세스 전역 싱글톤 ─────────────────────────────────────────────
_store_singleton: Optional[SQLiteStore] = None
_singleton_lock = threading.Lock()


def get_store() -> SQLiteStore:
    """프로세스 전역 SQLiteStore 싱글톤 팩토리."""
    global _store_singleton
    if _store_singleton is None:
        with _singleton_lock:
            if _store_singleton is None:
                _store_singleton = SQLiteStore()
    return _store_singleton
