"""Tests for the `thin_features` field on BoardStore.audit().

A Feature with exactly one US is the FRAGMENTATION smell ONLY when its epic holds >=2 such
single-US features (an epic split into many one-US features). A lone single-US feature is fine;
a feature with >=2 US is fine. `thin_features` is informational (like `expensive_us`) and does
NOT flip `ok`. Self-contained (stdlib + pytest), board on tmp_path, deterministic.
"""
from __future__ import annotations

from backend.board import BoardStore


def _store(tmp_path):
    return BoardStore(tmp_path / "board.json")


def _thin_ids(audit):
    return {f["id"] for f in audit["thin_features"]}


def test_epic_with_two_single_us_features_flags_both(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("Fragmented")
    f1 = s.add_feature(e.id, "F1")
    f2 = s.add_feature(e.id, "F2")
    s.add_story(f1.id, "only US of F1")
    s.add_story(f2.id, "only US of F2")
    au = s.audit()
    assert _thin_ids(au) == {f1.id, f2.id}
    # entries carry exactly {id, title, note}
    for entry in au["thin_features"]:
        assert set(entry) == {"id", "title", "note"}


def test_lone_single_us_feature_not_flagged(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("Standalone")
    f = s.add_feature(e.id, "F")
    s.add_story(f.id, "the only US")
    au = s.audit()
    assert f.id not in _thin_ids(au)
    assert au["thin_features"] == []


def test_feature_with_two_us_not_flagged(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("Healthy")
    f = s.add_feature(e.id, "F")
    s.add_story(f.id, "US A")
    s.add_story(f.id, "US B")
    au = s.audit()
    assert f.id not in _thin_ids(au)
    assert au["thin_features"] == []


def test_thin_features_is_informational_ok_stays_true(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("Fragmented but otherwise clean")
    f1 = s.add_feature(e.id, "F1")
    f2 = s.add_feature(e.id, "F2")
    s.add_story(f1.id, "only US of F1")
    s.add_story(f2.id, "only US of F2")
    au = s.audit()
    # the fragmentation pattern is present...
    assert _thin_ids(au) == {f1.id, f2.id}
    # ...but it does not flip ok: no coarse / orphan / empty smells
    assert au["coarse_us"] == []
    assert au["orphan_us"] == []
    assert au["empty_features"] == []
    assert au["ok"] is True


def test_mixed_epic_flags_only_the_single_us_features(tmp_path):
    s = _store(tmp_path)
    e = s.add_epic("Mixed")
    fat = s.add_feature(e.id, "Fat (2 US)")
    s.add_story(fat.id, "fat US A")
    s.add_story(fat.id, "fat US B")
    thin1 = s.add_feature(e.id, "Thin 1")
    thin2 = s.add_feature(e.id, "Thin 2")
    s.add_story(thin1.id, "thin US 1")
    s.add_story(thin2.id, "thin US 2")
    au = s.audit()
    assert _thin_ids(au) == {thin1.id, thin2.id}
    assert fat.id not in _thin_ids(au)
