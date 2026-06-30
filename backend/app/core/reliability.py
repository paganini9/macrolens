"""신뢰성 패턴 (NFR-2): Smart Retry + Circuit Breaker. Timeout 은 httpx timeout 으로."""
from __future__ import annotations
import time

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .exceptions import DataSourceError


def with_retry(max_attempts: int = 3):
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type(DataSourceError),
    )


class CircuitBreaker:
    def __init__(self, fail_max: int = 3, reset_timeout: float = 30.0):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._fails = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.time() - self._opened_at >= self.reset_timeout:
            self._opened_at = None
            self._fails = 0
            return False
        return True

    def record_success(self) -> None:
        self._fails = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._fails += 1
        if self._fails >= self.fail_max:
            self._opened_at = time.time()
