"""Tests for backend.board.BoardStore over a tmp board.json.

Self-contained (no conftest / __init__). Uses pytest tmp_path for the board file;
never touches the real data/ tree or ~/.claude.
"""
from __future__ import annotations

import json

import pytest

from backend.board import BoardStore
from backend.models import Board, Status, WorkLogEntry


@pytest.fixture
def store(tmp_path):
    return BoardStore(tmp_path / "board.json")


# --- create + hierarchy ----------------------------------------------------------------
def test_add_epic_feature_story_task(store):
    epic = store.add_epic("Platform", description="core", color="#abc123")
    assert epic.id == "epic-1"
    assert epic.title == "Platform"
    assert epic.description == "core"
    assert epic.color == "#abc123"
    assert epic.status == Status.backlog

    feat = store.add_feature(epic.id, "Auth")
    assert feat.id == "feat-1"
    assert feat.epic_id == epic.id

    story = store.add_story(feat.id, "Login", points=3, as_a="user", i_want="to log in")
    assert story.id == "us-1"
    assert story.feature_id == feat.id
    assert story.points == 3
    assert story.as_a == "user"

    task = store.add_task(story.id, "Build form", assignee="coder")
    assert task.id == "task-1"
    assert task.story_id == story.id
    assert task.assignee == "coder"

    b = store.load()
    assert len(b.epics) == 1
    assert len(b.features) == 1
    assert len(b.stories) == 1
    assert len(b.tasks) == 1


# --- id generation (collision-safe: max numeric suffix + 1) ----------------------------
def test_sequential_id_generation(store):
    e1 = store.add_epic("E1")
    e2 = store.add_epic("E2")
    e3 = store.add_epic("E3")
    assert [e1.id, e2.id, e3.id] == ["epic-1", "epic-2", "epic-3"]


def test_id_generation_collision_safe_after_delete(store):
    """After deleting the max-suffix item, the next id must still be max+1 (no reuse)."""
    e1 = store.add_epic("E1")
    e2 = store.add_epic("E2")
    e3 = store.add_epic("E3")
    assert e3.id == "epic-3"

    # Delete the highest-numbered epic, then add a new one.
    store.delete("epic", e3.id)
    e4 = store.add_epic("E4")
    # max remaining suffix is 2 (epic-2) -> next is epic-3, NOT a reuse of a stale max.
    assert e4.id == "epic-3"

    # Delete a middle epic; the highest remaining suffix still drives the next id.
    store.delete("epic", e2.id)  # remaining: epic-1, epic-3
    e5 = store.add_epic("E5")
    assert e5.id == "epic-4"

    _ = e1  # silence unused


def test_ids_namespaced_per_kind(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    task = store.add_task(story.id, "T")
    assert epic.id.startswith("epic-")
    assert feat.id.startswith("feat-")
    assert story.id.startswith("us-")
    assert task.id.startswith("task-")


# --- set_status ------------------------------------------------------------------------
def test_set_status(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    task = store.add_task(story.id, "T")

    store.set_status("epic", epic.id, Status.in_progress)
    store.set_status("feature", feat.id, Status.review)
    store.set_status("story", story.id, Status.done)
    store.set_status("task", task.id, Status.blocked)

    b = store.load()
    assert b.epics[0].status == Status.in_progress
    assert b.features[0].status == Status.review
    assert b.stories[0].status == Status.done
    assert b.tasks[0].status == Status.blocked


# --- assign (story/task only) ----------------------------------------------------------
def test_assign_story_and_task(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    task = store.add_task(story.id, "T")

    store.assign("story", story.id, "architect")
    store.assign("task", task.id, "coder")

    b = store.load()
    assert b.stories[0].assignee == "architect"
    assert b.tasks[0].assignee == "coder"


def test_assign_epic_or_feature_raises_value_error(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    with pytest.raises(ValueError):
        store.assign("epic", epic.id, "someone")
    with pytest.raises(ValueError):
        store.assign("feature", feat.id, "someone")


# --- log_work --------------------------------------------------------------------------
def test_log_work_appends_entry(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")

    entry = WorkLogEntry(
        agent="coder", session_id="sess-1", input_tokens=100, output_tokens=50,
        cost_usd=0.0123, note="did work", at="2026-06-27T00:00:00Z",
    )
    store.log_work("story", story.id, entry)

    b = store.load()
    assert len(b.stories[0].work_log) == 1
    logged = b.stories[0].work_log[0]
    assert logged.agent == "coder"
    assert logged.input_tokens == 100
    assert logged.output_tokens == 50
    assert logged.cost_usd == 0.0123

    # second entry appends (does not replace)
    store.log_work("story", story.id, WorkLogEntry(agent="reviewer"))
    assert len(store.load().stories[0].work_log) == 2


def test_log_work_on_task(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    task = store.add_task(story.id, "T")
    store.log_work("task", task.id, WorkLogEntry(agent="coder", cost_usd=1.0))
    assert store.load().tasks[0].work_log[0].cost_usd == 1.0


def test_log_work_epic_feature_raises_value_error(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    with pytest.raises(ValueError):
        store.log_work("epic", epic.id, WorkLogEntry(agent="x"))
    with pytest.raises(ValueError):
        store.log_work("feature", feat.id, WorkLogEntry(agent="x"))


# --- cascade delete --------------------------------------------------------------------
def test_delete_epic_cascades_all_descendants(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    store.add_task(story.id, "T")

    # an unrelated epic+children that must survive
    other_epic = store.add_epic("E2")
    other_feat = store.add_feature(other_epic.id, "F2")
    other_story = store.add_story(other_feat.id, "S2")
    other_task = store.add_task(other_story.id, "T2")

    store.delete("epic", epic.id)

    b = store.load()
    assert [e.id for e in b.epics] == [other_epic.id]
    assert [f.id for f in b.features] == [other_feat.id]
    assert [s.id for s in b.stories] == [other_story.id]
    assert [t.id for t in b.tasks] == [other_task.id]


def test_delete_feature_cascades_stories_and_tasks(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    store.add_task(story.id, "T")

    sibling = store.add_feature(epic.id, "F-sibling")

    store.delete("feature", feat.id)

    b = store.load()
    assert len(b.epics) == 1  # epic untouched
    assert [f.id for f in b.features] == [sibling.id]
    assert b.stories == []
    assert b.tasks == []


def test_delete_story_cascades_tasks_only(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    store.add_task(story.id, "T")
    sibling = store.add_story(feat.id, "S-sibling")

    store.delete("story", story.id)

    b = store.load()
    assert len(b.epics) == 1
    assert len(b.features) == 1
    assert [s.id for s in b.stories] == [sibling.id]
    assert b.tasks == []


def test_delete_task_removes_only_that_task(store):
    epic = store.add_epic("E")
    feat = store.add_feature(epic.id, "F")
    story = store.add_story(feat.id, "S")
    t1 = store.add_task(story.id, "T1")
    t2 = store.add_task(story.id, "T2")

    store.delete("task", t1.id)

    b = store.load()
    assert [t.id for t in b.tasks] == [t2.id]
    assert len(b.stories) == 1


# --- KeyError on missing parent / missing id -------------------------------------------
def test_add_feature_missing_parent_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.add_feature("epic-nope", "F")


def test_add_story_missing_parent_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.add_story("feat-nope", "S")


def test_add_task_missing_parent_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.add_task("us-nope", "T")


def test_set_status_missing_id_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.set_status("epic", "epic-nope", Status.done)


def test_assign_missing_id_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.assign("story", "us-nope", "coder")


def test_log_work_missing_id_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.log_work("task", "task-nope", WorkLogEntry(agent="x"))


def test_delete_missing_id_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.delete("epic", "epic-nope")


# --- save / load JSON round-trip -------------------------------------------------------
def test_save_load_round_trip(store):
    epic = store.add_epic("Platform", description="core")
    feat = store.add_feature(epic.id, "Auth")
    story = store.add_story(feat.id, "Login", points=5, assignee="architect")
    task = store.add_task(story.id, "Form", assignee="coder")
    store.log_work("task", task.id, WorkLogEntry(agent="coder", cost_usd=0.5))

    # Re-open via a brand-new store pointed at the same file.
    reopened = BoardStore(store.path)
    b = reopened.load()
    assert b.epics[0].title == "Platform"
    assert b.features[0].title == "Auth"
    assert b.stories[0].points == 5
    assert b.stories[0].assignee == "architect"
    assert b.tasks[0].work_log[0].cost_usd == 0.5


def test_saved_file_is_valid_json_with_expected_shape(store):
    epic = store.add_epic("E")
    store.add_feature(epic.id, "F")
    raw = store.path.read_text()
    data = json.loads(raw)
    assert set(data.keys()) == {"epics", "features", "stories", "tasks"}
    assert data["epics"][0]["id"] == "epic-1"
    assert data["features"][0]["epic_id"] == "epic-1"


def test_load_missing_file_returns_empty_board(tmp_path):
    s = BoardStore(tmp_path / "does_not_exist.json")
    assert not s.path.exists()
    b = s.load()
    assert isinstance(b, Board)
    assert b.epics == []
    assert b.features == []
    assert b.stories == []
    assert b.tasks == []


def test_load_corrupt_file_returns_empty_board(tmp_path):
    p = tmp_path / "board.json"
    p.write_text("{ this is not valid json ")
    b = BoardStore(p).load()
    assert isinstance(b, Board)
    assert b.epics == []
