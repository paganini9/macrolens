"""백엔드 API 소비 클라이언트 (api_standard v1).

Streamlit 비의존(순수 로직) — SSE 파싱·이벤트 누적·핀/헬스 호출을 담당해 단위 테스트 가능.
app.py 는 이 모듈을 import 해 점진 렌더링만 수행한다.

SSE 소비 계약: status* → (section|token|sources)* → done. error 는 어디서든 종료.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional

import httpx

# 섹터 유니버스(D1, MVP 8) — 백엔드와 동일(프론트는 백엔드 import 불가).
SECTOR_UNIVERSE = [
    "AI/SW", "반도체", "2차전지", "자동차",
    "금융", "에너지/화학", "바이오/헬스케어", "인터넷/플랫폼",
]


# --- SSE 파싱 (순수) --------------------------------------------------------
def iter_sse_events(lines: Iterable[str]) -> Iterator[dict]:
    """SSE 라인 스트림 → 이벤트 dict({'type':..., ...}) 제너레이터.

    각 프레임은 'event: <type>' + 'data: <json>' 이고 빈 줄로 구분된다.
    """
    etype: Optional[str] = None
    data_buf: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if line == "":
            if etype is not None and data_buf:
                yield _build_event(etype, "\n".join(data_buf))
            etype, data_buf = None, []
            continue
        if line.startswith(":"):  # 코멘트/keep-alive
            continue
        if line.startswith("event:"):
            etype = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_buf.append(line[len("data:"):].strip())
    if etype is not None and data_buf:  # 마지막 프레임(개행 누락 방어)
        yield _build_event(etype, "\n".join(data_buf))


def _build_event(etype: str, data: str) -> dict:
    try:
        payload = json.loads(data) if data else {}
    except json.JSONDecodeError:
        payload = {"raw": data}
    payload["type"] = etype
    return payload


# --- 브리핑 누적 상태 -------------------------------------------------------
@dataclass
class BriefingState:
    """이벤트를 화면 렌더 가능한 구조로 누적한다."""

    statuses: list[dict] = field(default_factory=list)
    body: str = ""
    transitions: list[dict] = field(default_factory=list)
    ranking: list[dict] = field(default_factory=list)
    coins: list[dict] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    scenario: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    summary: str = ""
    thread_id: str = ""
    trace_id: str = ""
    error: Optional[dict] = None

    def apply(self, event: dict) -> None:
        et = event.get("type")
        if et == "status":
            self.statuses.append({"stage": event.get("stage"), "msg": event.get("msg")})
        elif et == "token":
            self.body += event.get("text", "")
        elif et == "section":
            self._apply_section(event.get("kind"), event.get("payload", {}))
        elif et == "sources":
            self.sources = event.get("items", []) or self.sources
        elif et == "done":
            self.summary = event.get("summary", "")
            self.thread_id = event.get("thread_id", "")
            self.trace_id = event.get("trace_id", "")
        elif et == "error":
            self.error = {
                "code": event.get("code", "INTERNAL"),
                "user_message": event.get("user_message", "오류가 발생했습니다."),
                "trace_id": event.get("trace_id", ""),
            }

    def _apply_section(self, kind: str, payload: dict) -> None:
        if kind == "sector":
            if "scenario" in payload:
                self.scenario = payload.get("scenario", {}) or {}
            else:
                self.transitions = payload.get("transitions", []) or self.transitions
        elif kind == "ranking":
            self.ranking = payload.get("ranking", []) or self.ranking
        elif kind == "coin":
            self.coins = payload.get("coins", []) or self.coins
        elif kind == "change":
            self.changes = payload.get("changes", []) or self.changes


# --- HTTP 클라이언트 --------------------------------------------------------
class MacroLensClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict:
        r = httpx.get(f"{self.base_url}/api/v1/health", timeout=10.0)
        r.raise_for_status()
        return r.json()

    def get_pins(self) -> list[str]:
        r = httpx.get(f"{self.base_url}/api/v1/pins", timeout=10.0)
        r.raise_for_status()
        return r.json().get("pinned_sectors", [])

    def set_pins(self, sectors: list[str]) -> list[str]:
        r = httpx.put(
            f"{self.base_url}/api/v1/pins",
            json={"pinned_sectors": sectors},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json().get("pinned_sectors", [])

    def stream_chat(
        self,
        message: str,
        *,
        market_scope: Optional[list[str]] = None,
        depth: Optional[str] = None,
        mode: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Iterator[dict]:
        """POST /chat 를 SSE 로 소비해 이벤트 dict 를 점진 yield."""
        body: dict = {"message": message}
        if market_scope:
            body["market_scope"] = market_scope
        if depth:
            body["depth"] = depth
        if mode:
            body["mode"] = mode
        if thread_id:
            body["thread_id"] = thread_id
        with httpx.stream(
            "POST", f"{self.base_url}/api/v1/chat", json=body, timeout=self.timeout
        ) as resp:
            resp.raise_for_status()
            yield from iter_sse_events(resp.iter_lines())
