"""지표 코드 단위 TTL 캐시 (cache-first 읽기용).

외부 소스 호출 비용/레이트리밋을 줄이기 위한 간단한 인메모리 TTL 캐시.
멀티프로세스 영속성은 범위 밖(06 store 담당). 여기서는 프로세스 내 캐시만 책임진다.
"""
from __future__ import annotations

import time
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """지표 코드를 키로 하는 TTL 인메모리 캐시.

    - ``get`` 은 만료된 항목을 무시(None 반환)하고 자동 삭제한다.
    - ``set`` 은 항목과 함께 삽입 시각·해당 키의 TTL 을 기록한다.
    - ``set`` 에 ``ttl`` 을 주면 지표 클래스별(금리/환율/코인) 차등 만료가 가능하다.
      주지 않으면 생성자 기본 ``ttl_seconds`` 를 사용한다.
    - 기본 TTL 은 거시 지표 갱신 주기(월 1회 점검)를 고려해 넉넉히 둔다.
    """

    def __init__(self, ttl_seconds: float = 6 * 60 * 60) -> None:
        self.ttl_seconds = ttl_seconds
        # key -> (삽입시각, 적용 TTL, 값). TTL 을 항목마다 기록해 키별 차등 만료를 지원.
        self._store: dict[str, tuple[float, float, T]] = {}

    def get(self, key: str) -> Optional[T]:
        """만료되지 않은 값을 반환. 없거나 만료면 None."""
        hit = self._store.get(key)
        if hit is None:
            return None
        ts, ttl, value = hit
        if time.time() - ts >= ttl:
            # 만료 → 폐기
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T, ttl: Optional[float] = None) -> None:
        """값을 현재 시각·TTL 과 함께 저장. ``ttl`` 미지정 시 기본 TTL 사용."""
        effective = self.ttl_seconds if ttl is None else ttl
        self._store[key] = (time.time(), effective, value)

    def has(self, key: str) -> bool:
        """만료되지 않은 항목 존재 여부."""
        return self.get(key) is not None

    def clear(self) -> None:
        """전체 캐시 비우기(주로 테스트용)."""
        self._store.clear()
