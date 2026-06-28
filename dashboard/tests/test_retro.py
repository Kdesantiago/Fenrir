"""Tests for the epic-close retrospective (BoardStore.epic_retro_doc / write_epic_retro and the
auto-write on epic close). Self-contained: board + retro dir on tmp_path, explicit timestamps."""
from __future__ import annotations

from backend.board import BoardStore
from backend.models import Status


def _epic_with_two_us(s):
    e = s.add_epic("Payments revamp")
    f = s.add_feature(e.id, "Checkout API")
    a = s.add_story(f.id, "Add charge endpoint")
    b = s.add_story(f.id, "Add refund endpoint")
    return e, f, a, b


def test_epic_retro_doc_has_sections_and_rollup(tmp_path):
    s = BoardStore(tmp_path / "board.json")
    e, f, a, b = _epic_with_two_us(s)
    doc = s.epic_retro_doc(e.id)
    for heading in ("# Retrospective", "## What shipped", "## What worked",
                    "## What didn't / friction", "## Decisions to revisit", "## Timeline"):
        assert heading in doc
    assert "= Σ Features = Σ User Stories" in doc
    assert e.id in doc and f.id in doc and a.id in doc and b.id in doc


def test_write_epic_retro_does_not_clobber_without_force(tmp_path):
    retro = tmp_path / "retros"
    s = BoardStore(tmp_path / "board.json", retro_dir=retro)
    e, *_ = _epic_with_two_us(s)
    p = s.write_epic_retro(e.id)
    assert p.exists()
    p.write_text("HUMAN-REFINED NOTES")
    again = s.write_epic_retro(e.id)            # default: no clobber
    assert again.read_text() == "HUMAN-REFINED NOTES"
    forced = s.write_epic_retro(e.id, force=True)  # force regenerates
    assert "# Retrospective" in forced.read_text()


def test_auto_writes_retro_when_epic_closes(tmp_path):
    retro = tmp_path / "retros"
    s = BoardStore(tmp_path / "board.json", retro_dir=retro)
    e, f, a, b = _epic_with_two_us(s)
    s.set_status("story", a.id, Status.done, at="2026-01-01T00:00:00+00:00")
    assert not list(retro.glob("*.md"))  # one US done ≠ epic done → no retro yet
    s.set_status("story", b.id, Status.done, at="2026-01-02T00:00:00+00:00")
    files = list(retro.glob("*.md"))
    assert len(files) == 1 and files[0].name.startswith(e.id)
    assert "# Retrospective" in files[0].read_text()


def test_no_auto_write_without_retro_dir(tmp_path):
    s = BoardStore(tmp_path / "board.json")  # retro_dir=None → disabled
    e, f, a, b = _epic_with_two_us(s)
    s.set_status("story", a.id, Status.done, at="2026-01-01T00:00:00+00:00")
    s.set_status("story", b.id, Status.done, at="2026-01-02T00:00:00+00:00")
    assert next(x for x in s.load().epics if x.id == e.id).status == Status.done  # still closes
    # nothing written anywhere under tmp_path except the board file
    assert [p.name for p in tmp_path.iterdir()] == ["board.json"]


def test_retro_written_once_not_on_every_subsequent_change(tmp_path):
    retro = tmp_path / "retros"
    s = BoardStore(tmp_path / "board.json", retro_dir=retro)
    e, f, a, b = _epic_with_two_us(s)
    s.set_status("story", a.id, Status.done, at="2026-01-01T00:00:00+00:00")
    s.set_status("story", b.id, Status.done, at="2026-01-02T00:00:00+00:00")
    p = next(retro.glob("*.md"))
    p.write_text("REFINED")
    # reopen + reclose: was_done guard means the close re-fires, but no-clobber keeps the refined doc
    s.set_status("story", b.id, Status.in_progress, at="2026-01-03T00:00:00+00:00")
    s.set_status("story", b.id, Status.done, at="2026-01-04T00:00:00+00:00")
    assert p.read_text() == "REFINED"
