"""Tests for BoardStore.trace — the work-log cost trace (arrivals view).

Covers the scoped/sorted signature:
    trace(us_id=None, feature_id=None, epic_id=None, newest_first=True) -> list[dict]

Deterministic and self-contained: board on tmp_path, explicit `at` timestamps on every
WorkLogEntry so ordering is fully determined (no clock). Stdlib + pytest only.
"""
from __future__ import annotations

from backend.board import BoardStore
from backend.models import WorkLogEntry


def _store(tmp_path):
    return BoardStore(tmp_path / "board.json")


def _entry(at: str, **kw) -> WorkLogEntry:
    return WorkLogEntry(at=at, **kw)


def _two_epic_board(tmp_path):
    """Two epics, each with one feature + one story, plus a task under the first story.

    Returns the store and the ids so tests can assert roll-up + filtering.
    Work-log timestamps are spread across distinct days for deterministic ordering.
    """
    s = _store(tmp_path)
    e1 = s.add_epic("E1")
    f1 = s.add_feature(e1.id, "F1")
    a = s.add_story(f1.id, "Story A")
    t = s.add_task(a.id, "Task A1")

    e2 = s.add_epic("E2")
    f2 = s.add_feature(e2.id, "F2")
    b = s.add_story(f2.id, "Story B")

    # Story A: two entries (oldest 01-01, then 01-03). Task A1: one entry (01-02, in the middle).
    s.log_work("story", a.id, _entry("2026-01-01T00:00:00+00:00", agent="architect", cost_usd=1.0))
    s.log_work("story", a.id, _entry("2026-01-03T00:00:00+00:00", agent="coder", cost_usd=3.0))
    s.log_work("task", t.id, _entry("2026-01-02T00:00:00+00:00", agent="coder", cost_usd=2.0))
    # Story B: one entry (01-04, newest overall).
    s.log_work("story", b.id, _entry("2026-01-04T00:00:00+00:00", agent="reviewer", cost_usd=4.0))

    return s, {"e1": e1.id, "f1": f1.id, "a": a.id, "t": t.id,
               "e2": e2.id, "f2": f2.id, "b": b.id}


def test_newest_first_is_default(tmp_path):
    s, ids = _two_epic_board(tmp_path)
    rows = s.trace()  # default newest_first=True
    ats = [r["at"] for r in rows]
    assert ats == sorted(ats, reverse=True)
    assert ats[0] == "2026-01-04T00:00:00+00:00"   # Story B entry is newest
    assert ats[-1] == "2026-01-01T00:00:00+00:00"  # Story A's first entry is oldest


def test_oldest_first_when_newest_first_false(tmp_path):
    s, ids = _two_epic_board(tmp_path)
    rows = s.trace(newest_first=False)
    ats = [r["at"] for r in rows]
    assert ats == sorted(ats)  # ascending
    assert ats[0] == "2026-01-01T00:00:00+00:00"
    assert ats[-1] == "2026-01-04T00:00:00+00:00"


def test_filter_by_epic_id(tmp_path):
    s, ids = _two_epic_board(tmp_path)
    rows = s.trace(epic_id=ids["e1"])
    # E1 contains Story A (2 entries) + Task A1 (1 entry) = 3; Story B (E2) excluded.
    assert len(rows) == 3
    assert {r["epic_id"] for r in rows} == {ids["e1"]}
    assert all(r["us_id"] == ids["a"] for r in rows)


def test_filter_by_feature_id(tmp_path):
    s, ids = _two_epic_board(tmp_path)
    rows = s.trace(feature_id=ids["f2"])
    # F2 contains only Story B (1 entry).
    assert len(rows) == 1
    assert rows[0]["feature_id"] == ids["f2"]
    assert rows[0]["us_id"] == ids["b"]
    assert rows[0]["epic_id"] == ids["e2"]


def test_filter_by_us_id(tmp_path):
    s, ids = _two_epic_board(tmp_path)
    rows = s.trace(us_id=ids["a"])
    # Story A's own work_log only (its 2 entries). The task is a separate row source; it
    # carries us_id == Story A and is therefore kept too.
    assert {r["us_id"] for r in rows} == {ids["a"]}
    kinds = sorted(r["kind"] for r in rows)
    assert kinds == ["story", "story", "task"]  # 2 story entries + 1 rolled-up task entry
    assert len(rows) == 3


def test_each_row_carries_grouping_keys(tmp_path):
    s, ids = _two_epic_board(tmp_path)
    rows = s.trace()
    required = {"us_id", "feature_id", "epic_id", "kind", "title"}
    for r in rows:
        assert required <= r.keys(), f"row missing keys: {required - r.keys()}"
    # Spot-check the Story B row's correctness (newest, unambiguous).
    b_row = next(r for r in rows if r["us_id"] == ids["b"])
    assert b_row["feature_id"] == ids["f2"]
    assert b_row["epic_id"] == ids["e2"]
    assert b_row["kind"] == "story"
    assert b_row["title"] == "Story B"


def test_task_work_log_rolls_up_to_parent_story(tmp_path):
    s, ids = _two_epic_board(tmp_path)
    rows = s.trace()
    task_rows = [r for r in rows if r["kind"] == "task"]
    assert len(task_rows) == 1
    tr = task_rows[0]
    # The task's entry is attributed to its parent story's full lineage.
    assert tr["us_id"] == ids["a"]
    assert tr["feature_id"] == ids["f1"]
    assert tr["epic_id"] == ids["e1"]
    assert tr["title"] == "Story A"   # titled by the parent story, not the task
    assert tr.get("task_id") == ids["t"]
    assert tr["cost_usd"] == 2.0
