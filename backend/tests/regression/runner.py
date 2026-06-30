"""회귀셋 러너 — regression_set.jsonl 의 각 케이스를 그래프로 결정적 실행하고
expected 단언을 검증한다(MockLLM + fixture/empty deps → 오프라인·재현 가능).

수용기준(AC-*) → 통합 검증. 실패는 메시지 리스트로 반환(빈 리스트=통과).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from app.graph.build import build_graph
from app.graph.fixtures import FixtureCollector, FixtureRetriever, _METRICS
from app.graph.nodes import DEFAULT_INDICATORS
from app.graph.state import initial_state
from app.llm import prompts
from app.llm.provider import MockLLM
from app.store.mocks import MockStore

REGRESSION_PATH = os.path.join(os.path.dirname(__file__), "regression_set.jsonl")

# 단정/추천 금지 표현(안전). 등장 시 assertive_forbidden 위반.
ASSERTIVE_KW = ["반드시 사", "꼭 사", "추천합니다", "보장합니다", "확실히 오른다", "무조건"]
# 출처처럼 보이는 토큰(숫자 오탐 방지용 제거 대상): causal-0001 등.
_ID_RE = re.compile(r"[a-zA-Z]+-\d+")
_NUM_RE = re.compile(r"\d+\.\d+|\d+%")


class _EmptyCollector:
    def __init__(self):
        self._gaps: list[str] = []

    def collect(self, market_scope, indicators):
        self._gaps = list(indicators or [])
        return {}

    def gaps(self):
        return list(self._gaps)


class _EmptyRetriever:
    def query(self, macro_state, sectors, k=6, weights=None):
        return []

    def is_sufficient(self, hits, sectors):
        return False

    def index_incremental(self):
        return 0

    def ensure_synced(self):
        return None


@dataclass
class RunResult:
    events: list[dict] = field(default_factory=list)
    body: str = ""
    safe_message: str = ""
    blocked: bool = False
    transitions: list[dict] = field(default_factory=list)
    ranking: list[dict] = field(default_factory=list)
    coins: list[dict] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    scenario: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    summary: str = ""
    allowed_numbers: set[str] = field(default_factory=set)
    has_section: bool = False

    @property
    def combined_text(self) -> str:
        parts = [self.body, self.safe_message, self.summary, json.dumps(self.scenario, ensure_ascii=False)]
        parts += [json.dumps(x, ensure_ascii=False) for x in (self.transitions, self.ranking, self.coins, self.changes)]
        parts += [s.get("title", "") + s.get("ref", "") for s in self.sources]
        return "\n".join(parts)


def load_cases(path: str = REGRESSION_PATH) -> list[dict]:
    cases: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def run_case(case: dict) -> RunResult:
    inp = case["input"]
    insufficient = inp.get("data_state") == "insufficient"
    collector = _EmptyCollector() if insufficient else FixtureCollector()
    retriever = _EmptyRetriever() if insufficient else FixtureRetriever()
    app = build_graph(llm=MockLLM(), collector=collector, retriever=retriever, store=MockStore())
    state = initial_state(
        thread_id=case["id"],
        user_input=inp["message"],
        market_scope=inp.get("market"),
        depth=inp.get("depth", "evidence"),
        intent=case.get("mode"),
    )
    res = RunResult()
    res.allowed_numbers = set() if insufficient else {
        str(_METRICS[c]["value"]) for c in DEFAULT_INDICATORS if c in _METRICS
    }
    for e in app.stream(state):
        res.events.append(e)
        et = e.get("type")
        if et == "token":
            res.body += e.get("text", "")
        elif et == "section":
            res.has_section = True
            _apply_section(res, e.get("kind"), e.get("payload", {}))
        elif et == "sources":
            res.sources = e.get("items", []) or res.sources
        elif et == "done":
            res.summary = e.get("summary", "")
        elif et == "status" and e.get("stage") == "analyze" and e.get("msg") == "안전 점검":
            pass
    # blocked 판정: safety 차단 시 token=safe_message, 분석 섹션 없음
    if not res.has_section and prompts.GUARDRAIL_SAFE_MESSAGE[:12] in res.body:
        res.blocked = True
        res.safe_message = res.body
    return res


def _apply_section(res: RunResult, kind: str, payload: dict) -> None:
    if kind == "sector":
        if "scenario" in payload:
            res.scenario = payload.get("scenario", {}) or {}
        else:
            res.transitions = payload.get("transitions", []) or res.transitions
    elif kind == "ranking":
        res.ranking = payload.get("ranking", []) or res.ranking
    elif kind == "coin":
        res.coins = payload.get("coins", []) or res.coins
    elif kind == "change":
        res.changes = payload.get("changes", []) or res.changes


def check_case(case: dict, res: RunResult) -> list[str]:
    """expected 단언 검증. 반환=실패 메시지 리스트(빈=통과)."""
    exp = case.get("expected", {})
    text = res.combined_text
    fails: list[str] = []

    for term in exp.get("must_include", []):
        if term not in text:
            fails.append(f"must_include '{term}' 누락")

    for sec in exp.get("sectors_covered", []):
        if sec not in text:
            fails.append(f"sectors_covered '{sec}' 미커버")

    if exp.get("blocked") and not res.blocked:
        fails.append("blocked 기대했으나 미차단")
    if exp.get("sections_absent") and res.has_section:
        fails.append("분석 섹션이 없어야 하나 존재")
    if exp.get("ranking_present") and not res.ranking:
        fails.append("ranking 비어있음")
    if exp.get("ranking_absent") and res.ranking:
        fails.append("ranking 이 있어선 안 됨(배타성 위반)")
    if exp.get("coin_separated") and not res.coins:
        fails.append("coin 분리 섹션 없음")
    if exp.get("sources_present") and not res.sources:
        fails.append("출처 미부착")
    if exp.get("disclaimer_required") and prompts.DISCLAIMER not in res.body:
        fails.append("면책 누락")

    if exp.get("uncertainty"):
        ok = bool(res.scenario.get("uncertainty")) or "불확실" in text or "근거 부족" in text
        if not ok:
            fails.append("불확실성 표현 없음")

    if exp.get("assertive_forbidden"):
        hit = [k for k in ASSERTIVE_KW if k in res.body]
        if hit:
            fails.append(f"단정/추천 표현 등장: {hit}")

    if exp.get("no_hallucinated_numbers"):
        scrubbed = _ID_RE.sub("", res.body)
        nums = set(_NUM_RE.findall(scrubbed))
        bad = {n for n in nums if n not in res.allowed_numbers and n.rstrip("%") not in {x.rstrip('%') for x in res.allowed_numbers}}
        if bad:
            fails.append(f"근거 없는 수치 등장: {sorted(bad)} (허용 {sorted(res.allowed_numbers)})")

    return fails


def run_all(path: str = REGRESSION_PATH) -> dict[str, list[str]]:
    """전체 회귀셋 실행 → {case_id: 실패메시지[]}."""
    out: dict[str, list[str]] = {}
    for case in load_cases(path):
        out[case["id"]] = check_case(case, run_case(case))
    return out
