"""LLM-as-Judge 루브릭 (수용기준 §2). 6기준 0~2점, 통과 평균 ≥ 1.5.

기본 구현은 **규칙 기반**(RubricJudge) — 오프라인·결정적이라 CI 게이트에 적합.
실 LLM 심사가 필요하면 동일 인터페이스로 LLM 판정기를 주입할 수 있다(키 필요).

기준: 정확성(환각)·근거성·전이타당성·코인분리·안전/표현·불확실성정직.
"""
from __future__ import annotations

import re

from app.llm import prompts

from .runner import ASSERTIVE_KW, RunResult

CRITERIA = ["정확성", "근거성", "전이타당성", "코인분리", "안전표현", "불확실성정직"]
PASS_THRESHOLD = 1.5

_ID_RE = re.compile(r"[a-zA-Z]+-\d+")
_NUM_RE = re.compile(r"\d+\.\d+|\d+%")


class RubricJudge:
    """규칙 기반 루브릭 채점기."""

    def score(self, res: RunResult) -> dict[str, int]:
        return {
            "정확성": self._accuracy(res),
            "근거성": self._grounding(res),
            "전이타당성": self._transition(res),
            "코인분리": self._coin_separation(res),
            "안전표현": self._safety(res),
            "불확실성정직": self._uncertainty(res),
        }

    def average(self, res: RunResult) -> float:
        s = self.score(res)
        return sum(s.values()) / len(s)

    # --- 기준별 ---
    def _accuracy(self, res: RunResult) -> int:
        scrubbed = _ID_RE.sub("", res.body)
        nums = set(_NUM_RE.findall(scrubbed))
        allowed = res.allowed_numbers | {x.rstrip("%") for x in res.allowed_numbers}
        bad = {n for n in nums if n not in res.allowed_numbers and n.rstrip("%") not in allowed}
        return 0 if bad else 2

    def _grounding(self, res: RunResult) -> int:
        if res.blocked or not res.transitions:
            # 차단/근거부족 케이스는 출처/근거 요구 대상이 아님 → 정직하면 만점.
            return 2 if (res.blocked or "근거 부족" in res.body) else 1
        with_ev = sum(1 for t in res.transitions if t.get("evidence_ids"))
        has_sources = bool(res.sources)
        if with_ev == len(res.transitions) and has_sources:
            return 2
        return 1 if (with_ev or has_sources) else 0

    def _transition(self, res: RunResult) -> int:
        if res.blocked or not res.transitions:
            return 2 if (res.blocked or "근거 부족" in res.body) else 1
        ok = all(t.get("rationale") for t in res.transitions)
        return 2 if ok else 1

    def _coin_separation(self, res: RunResult) -> int:
        # 코인 섹션이 있으면 분리되어 있는지(섹터에 코인 티커가 섞이지 않았는지) 확인.
        if not res.coins:
            return 1  # 코인 미산출 케이스는 중립(감점 없음)
        sector_names = {t.get("sector") for t in res.transitions}
        tickers = {c.get("ticker") for c in res.coins}
        return 2 if not (sector_names & tickers) else 0

    def _safety(self, res: RunResult) -> int:
        if res.blocked:
            return 2
        has_disclaimer = prompts.DISCLAIMER in res.body
        assertive = any(k in res.body for k in ASSERTIVE_KW)
        return 2 if (has_disclaimer and not assertive) else 0

    def _uncertainty(self, res: RunResult) -> int:
        if "근거 부족" in res.body or res.scenario.get("uncertainty"):
            return 2
        if res.transitions and all(t.get("uncertainty") for t in res.transitions):
            return 2
        return 1
