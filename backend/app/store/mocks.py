"""계약을 만족하는 인메모리 Store mock.

의존 레이어(그래프·API)가 SQLite 없이도 Store 계약으로 개발/테스트할 수 있도록
제공한다. 기본 핀으로 시드되며 브리핑은 비어 있다.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

# MVP 기본 관심 섹터(시드).
_DEFAULT_PINS = ["반도체", "2차전지", "AI/SW"]


class MockStore:
    """Store Protocol 의 인메모리 구현(비영속). 테스트·mock 전용."""

    def __init__(self) -> None:
        self._pins: list[str] = list(_DEFAULT_PINS)
        # (created_at, seq, payload) 튜플 목록. seq = 삽입 순서(동일 타임스탬프 tie-break).
        self._briefings: list[tuple[str, int, dict]] = []
        self._seq: int = 0

    def get_pins(self) -> list[str]:
        return list(self._pins)

    def set_pins(self, sectors: list[str]) -> None:
        self._pins = list(sectors)

    def save_briefing(self, thread_id: str, briefing: dict) -> str:
        bid = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        # round-trip 격리를 위해 깊은 복사(직렬화) 후 저장.
        payload = json.loads(json.dumps(briefing, ensure_ascii=False))
        payload.setdefault("thread_id", thread_id)
        self._seq += 1
        self._briefings.append((created_at, self._seq, payload))
        return bid

    def last_briefing(self) -> dict | None:
        if not self._briefings:
            return None
        latest = max(self._briefings, key=lambda r: (r[0], r[1]))
        return latest[2]

    def list_briefings(self, limit: int = 20) -> list[dict]:
        ordered = sorted(self._briefings, key=lambda r: (r[0], r[1]), reverse=True)
        return [payload for _, _, payload in ordered[:limit]]


__all__ = ["MockStore"]
