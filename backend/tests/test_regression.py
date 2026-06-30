"""회귀셋 + LLM-as-Judge 게이트 (T-70 / 08 QA).

- regression_set.jsonl 의 모든 케이스가 expected 단언을 통과해야 한다.
- 정규 브리핑 케이스는 루브릭 평균 ≥ 1.5(통과 기준).
실패는 게이트 차단(수용기준 §1·§2).
"""
from __future__ import annotations

import pytest

from regression.judge import CRITERIA, PASS_THRESHOLD, RubricJudge
from regression.runner import check_case, load_cases, run_all, run_case

CASES = load_cases()


def test_regression_set_nonempty():
    assert len(CASES) >= 6


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_regression_case(case):
    res = run_case(case)
    fails = check_case(case, res)
    assert not fails, f"{case['id']} 실패: {fails}"


def test_run_all_green():
    results = run_all()
    failed = {cid: f for cid, f in results.items() if f}
    assert not failed, f"회귀 실패: {failed}"


@pytest.mark.parametrize("case_id", ["reg-001", "reg-005"])
def test_judge_rubric_passes_for_briefings(case_id):
    case = next(c for c in CASES if c["id"] == case_id)
    res = run_case(case)
    judge = RubricJudge()
    scores = judge.score(res)
    assert set(scores) == set(CRITERIA)
    avg = judge.average(res)
    assert avg >= PASS_THRESHOLD, f"{case_id} 루브릭 평균 {avg:.2f} < {PASS_THRESHOLD} (점수 {scores})"


def test_judge_safety_zero_when_no_disclaimer():
    # 면책 누락 시 안전/표현 0점(AC-G2 게이트 동작 확인)
    case = next(c for c in CASES if c["id"] == "reg-001")
    res = run_case(case)
    res.body = res.body.replace("투자 권유가 아니며 판단 재료를 제공합니다.", "")
    assert RubricJudge()._safety(res) == 0
