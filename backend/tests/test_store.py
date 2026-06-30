"""Store 레이어 테스트: 핀 round-trip·교체, 브리핑 저장/최신/목록, 재시작 영속성.

venv(3.12)에서 `./.venv/Scripts/python.exe -m pytest -q backend/tests/test_store.py`.
"""
from __future__ import annotations

import pytest

from app.store import MockStore, SQLiteStore, Store


def _new_store(tmp_path) -> SQLiteStore:
    return SQLiteStore(db_path=str(tmp_path / "macrolens_test.db"))


# ── 핀(관심 섹터) ────────────────────────────────────────────────────
def test_pins_round_trip_and_ordering(tmp_path):
    store = _new_store(tmp_path)
    assert store.get_pins() == []  # 초기 비어 있음

    store.set_pins(["반도체", "AI/SW", "2차전지"])
    # 입력 순서(ord 0,1,2) 그대로 보존되어야 한다.
    assert store.get_pins() == ["반도체", "AI/SW", "2차전지"]


def test_set_pins_replace_semantics(tmp_path):
    store = _new_store(tmp_path)
    store.set_pins(["반도체", "자동차", "금융"])
    # 전체 교체: 이전 항목은 남지 않는다.
    store.set_pins(["바이오/헬스케어", "에너지/화학"])
    assert store.get_pins() == ["바이오/헬스케어", "에너지/화학"]

    # 빈 목록으로 모두 제거 가능.
    store.set_pins([])
    assert store.get_pins() == []


# ── 브리핑 히스토리 ──────────────────────────────────────────────────
def test_save_last_and_list_ordering(tmp_path):
    store = _new_store(tmp_path)
    assert store.last_briefing() is None
    assert store.list_briefings() == []

    id1 = store.save_briefing("t1", {"summary": "첫째", "trigger_type": "scheduled"})
    id2 = store.save_briefing("t2", {"summary": "둘째"})
    id3 = store.save_briefing("t3", {"summary": "셋째", "trigger_type": "manual"})
    assert len({id1, id2, id3}) == 3  # id 는 고유

    # 최신 = 마지막 저장.
    assert store.last_briefing()["summary"] == "셋째"

    # 최신순 목록.
    summaries = [b["summary"] for b in store.list_briefings()]
    assert summaries == ["셋째", "둘째", "첫째"]


def test_list_briefings_limit(tmp_path):
    store = _new_store(tmp_path)
    for i in range(5):
        store.save_briefing(f"t{i}", {"summary": f"b{i}"})
    limited = store.list_briefings(limit=2)
    assert len(limited) == 2
    assert [b["summary"] for b in limited] == ["b4", "b3"]


def test_payload_preserves_unicode_and_trigger_type(tmp_path):
    store = _new_store(tmp_path)
    store.save_briefing("t", {"한글": "값", "trigger_type": "change"})
    last = store.last_briefing()
    assert last["한글"] == "값"
    assert last["trigger_type"] == "change"


# ── 재시작 영속성 (핵심 DoD) ─────────────────────────────────────────
def test_persistence_across_restart(tmp_path):
    db = str(tmp_path / "persist.db")

    s1 = SQLiteStore(db_path=db)
    s1.set_pins(["반도체", "2차전지"])
    s1.save_briefing("t1", {"summary": "이전 브리핑", "trigger_type": "scheduled"})

    # 같은 파일로 새 커넥션(=프로세스 재시작 시뮬레이션).
    s2 = SQLiteStore(db_path=db)
    assert s2.get_pins() == ["반도체", "2차전지"]
    assert s2.last_briefing()["summary"] == "이전 브리핑"
    assert len(s2.list_briefings()) == 1


# ── MockStore 계약 만족 ──────────────────────────────────────────────
def test_mockstore_satisfies_contract():
    mock = MockStore()
    assert isinstance(mock, Store)  # runtime_checkable Protocol

    # 기본 핀 시드.
    assert mock.get_pins() == ["반도체", "2차전지", "AI/SW"]

    mock.set_pins(["자동차"])
    assert mock.get_pins() == ["자동차"]

    assert mock.last_briefing() is None
    mock.save_briefing("t1", {"summary": "a"})
    mock.save_briefing("t2", {"summary": "b"})
    assert mock.last_briefing()["summary"] == "b"
    assert [x["summary"] for x in mock.list_briefings()] == ["b", "a"]
    assert len(mock.list_briefings(limit=1)) == 1


@pytest.mark.parametrize("impl", ["sqlite", "mock"])
def test_both_impls_are_store_instances(tmp_path, impl):
    store = _new_store(tmp_path) if impl == "sqlite" else MockStore()
    assert isinstance(store, Store)
