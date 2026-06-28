"""Tests for BoardStore.flow_metrics — cycle time, throughput, WIP/aging, forecast.

Deterministic: transition timestamps are supplied explicitly and `now`/`seed` are passed in,
so no clock or RNG nondeterminism. Self-contained (stdlib + pytest), board on tmp_path.
"""
from __future__ import annotations

from backend.board import BoardStore
from backend.models import Status


def _store(tmp_path):
    return BoardStore(tmp_path / "board.json")


def _story(s, title="S"):
    e = s.add_epic("E")
    f = s.add_feature(e.id, "F")
    return s.add_story(f.id, title)


def test_cycle_time_from_in_progress_to_done(tmp_path):
    s = _store(tmp_path)
    st = _story(s)
    s.set_status("story", st.id, Status.in_progress, at="2026-01-01T00:00:00+00:00")
    s.set_status("story", st.id, Status.done, at="2026-01-03T00:00:00+00:00")  # 2 days
    m = s.flow_metrics(now="2026-01-10T00:00:00+00:00")
    assert m["cycle_time_days"]["count"] == 1
    assert m["cycle_time_days"]["avg"] == 2.0
    assert m["wip"]["count"] == 0
    assert sum(m["throughput_per_week"]["weeks"].values()) == 1


def test_transitions_recorded_only_on_real_change(tmp_path):
    s = _store(tmp_path)
    st = _story(s)
    s.set_status("story", st.id, Status.todo, at="2026-01-01T00:00:00+00:00")
    s.set_status("story", st.id, Status.todo, at="2026-01-02T00:00:00+00:00")  # no-op move
    reloaded = next(x for x in s.load().stories if x.id == st.id)
    assert len(reloaded.transitions) == 1  # the no-op didn't add a second


def test_wip_and_aging(tmp_path):
    s = _store(tmp_path)
    st = _story(s)
    s.set_status("story", st.id, Status.in_progress, at="2026-01-01T00:00:00+00:00")
    m = s.flow_metrics(now="2026-01-06T00:00:00+00:00")  # 5 days in progress
    assert m["wip"]["count"] == 1 and m["wip"]["items"] == [st.id]
    assert m["aging_wip"][0]["age_days"] == 5.0


def test_forecast_is_reproducible_with_seed(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("E")
    f = s.add_feature(e.id, "F")
    for i in range(3):  # 3 completed in one week → throughput sample [3]
        st = s.add_story(f.id, f"D{i}")
        s.set_status("story", st.id, Status.in_progress, at="2026-01-01T00:00:00+00:00")
        s.set_status("story", st.id, Status.done, at=f"2026-01-0{2 + i}T00:00:00+00:00")
    for i in range(2):  # 2 remaining
        s.add_story(f.id, f"R{i}")
    m1 = s.flow_metrics(now="2026-02-01T00:00:00+00:00", seed=1)
    m2 = s.flow_metrics(now="2026-02-01T00:00:00+00:00", seed=1)
    assert m1["forecast"]["items_remaining"] == 2
    assert m1["forecast"]["weeks_p50"] is not None
    assert m1["forecast"] == m2["forecast"]  # deterministic given the seed


def test_status_rolls_up_us_to_feature_to_epic(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    a = s.add_story(f.id, "A"); b = s.add_story(f.id, "B")
    # one US active → feature + epic become in_progress
    s.set_status("story", a.id, Status.in_progress, at="2026-01-01T00:00:00+00:00")
    bd = s.load()
    assert next(x for x in bd.features if x.id == f.id).status == Status.in_progress
    assert next(x for x in bd.epics if x.id == e.id).status == Status.in_progress
    # all US done → feature + epic close automatically
    s.set_status("story", a.id, Status.done, at="2026-01-02T00:00:00+00:00")
    s.set_status("story", b.id, Status.done, at="2026-01-02T00:00:00+00:00")
    bd = s.load()
    assert next(x for x in bd.features if x.id == f.id).status == Status.done
    assert next(x for x in bd.epics if x.id == e.id).status == Status.done


def test_manual_feature_drag_rolls_up_to_epic(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    s.set_status("feature", f.id, Status.in_progress, at="2026-01-01T00:00:00+00:00")
    assert next(x for x in s.load().epics if x.id == e.id).status == Status.in_progress


def test_empty_board_does_not_crash(tmp_path):
    m = _store(tmp_path).flow_metrics(now="2026-01-01T00:00:00+00:00")
    assert m["cycle_time_days"]["count"] == 0
    assert m["wip"]["count"] == 0
    assert m["forecast"] == {}
