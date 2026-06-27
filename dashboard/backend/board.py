"""Agile board store — Epic → Feature → User Story → Task over a git-tracked JSON file.

LifeOS spirit: the board is plain, reviewable, version-controlled data (`data/board.json`),
not a hidden DB. Both the web API and the CLI (which the agents drive) go through this one
module, so there is a single source of truth.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Board, Epic, Feature, Status, Task, UserStory, WorkLogEntry

DEFAULT_BOARD_PATH = Path(__file__).resolve().parent.parent / "data" / "board.json"

_PREFIX = {"epic": "epic", "feature": "feat", "story": "us", "task": "task"}


class BoardStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_BOARD_PATH

    # --- persistence -------------------------------------------------------------------
    def load(self) -> Board:
        if not self.path.exists():
            return Board()
        try:
            return Board.model_validate_json(self.path.read_text())
        except Exception:
            return Board()

    def save(self, board: Board) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(board.model_dump_json(indent=2) + "\n")

    # --- id generation (collision-safe: max numeric suffix + 1) ------------------------
    def _next_id(self, kind: str, existing: list[str]) -> str:
        prefix = _PREFIX[kind]
        n = 0
        for i in existing:
            if i.startswith(prefix + "-"):
                try:
                    n = max(n, int(i.rsplit("-", 1)[1]))
                except ValueError:
                    pass
        return f"{prefix}-{n + 1}"

    # --- create ------------------------------------------------------------------------
    def add_epic(self, title: str, description: str = "", color: str = "#6366f1",
                 created: str = "") -> Epic:
        b = self.load()
        epic = Epic(id=self._next_id("epic", [e.id for e in b.epics]), title=title,
                    description=description, color=color, created=created)
        b.epics.append(epic)
        self.save(b)
        return epic

    def add_feature(self, epic_id: str, title: str, description: str = "") -> Feature:
        b = self.load()
        if not any(e.id == epic_id for e in b.epics):
            raise KeyError(f"epic {epic_id} not found")
        feat = Feature(id=self._next_id("feature", [f.id for f in b.features]),
                       epic_id=epic_id, title=title, description=description)
        b.features.append(feat)
        self.save(b)
        return feat

    def add_story(self, feature_id: str, title: str, assignee: str = "", points: int = 0,
                  as_a: str = "", i_want: str = "", so_that: str = "",
                  acceptance_criteria: list[str] | None = None) -> UserStory:
        b = self.load()
        if not any(f.id == feature_id for f in b.features):
            raise KeyError(f"feature {feature_id} not found")
        story = UserStory(
            id=self._next_id("story", [s.id for s in b.stories]), feature_id=feature_id,
            title=title, assignee=assignee, points=points, as_a=as_a, i_want=i_want,
            so_that=so_that, acceptance_criteria=acceptance_criteria or [],
        )
        b.stories.append(story)
        self.save(b)
        return story

    def add_task(self, story_id: str, title: str, assignee: str = "") -> Task:
        b = self.load()
        if not any(s.id == story_id for s in b.stories):
            raise KeyError(f"story {story_id} not found")
        task = Task(id=self._next_id("task", [t.id for t in b.tasks]), story_id=story_id,
                    title=title, assignee=assignee)
        b.tasks.append(task)
        self.save(b)
        return task

    # --- mutate ------------------------------------------------------------------------
    def _collection(self, b: Board, kind: str) -> list[Any]:
        coll: dict[str, list[Any]] = {"epic": b.epics, "feature": b.features,
                                      "story": b.stories, "task": b.tasks}
        return coll[kind]

    def _find(self, b: Board, kind: str, item_id: str) -> Any:
        for item in self._collection(b, kind):
            if item.id == item_id:
                return item
        raise KeyError(f"{kind} {item_id} not found")

    def set_status(self, kind: str, item_id: str, status: Status) -> Any:
        b = self.load()
        item = self._find(b, kind, item_id)
        item.status = status
        self.save(b)
        return item

    def assign(self, kind: str, item_id: str, assignee: str) -> Any:
        if kind not in ("story", "task"):
            raise ValueError("only stories and tasks take an assignee")
        b = self.load()
        item = self._find(b, kind, item_id)
        item.assignee = assignee
        self.save(b)
        return item

    def log_work(self, kind: str, item_id: str, entry: WorkLogEntry) -> Any:
        if kind not in ("story", "task"):
            raise ValueError("work can only be logged on stories and tasks")
        b = self.load()
        item = self._find(b, kind, item_id)
        item.work_log.append(entry)
        self.save(b)
        return item

    def delete(self, kind: str, item_id: str) -> None:
        """Delete an item and cascade to its children."""
        b = self.load()
        self._find(b, kind, item_id)  # raises if absent
        if kind == "epic":
            feats = {f.id for f in b.features if f.epic_id == item_id}
            stories = {s.id for s in b.stories if s.feature_id in feats}
            b.tasks = [t for t in b.tasks if t.story_id not in stories]
            b.stories = [s for s in b.stories if s.id not in stories]
            b.features = [f for f in b.features if f.id not in feats]
            b.epics = [e for e in b.epics if e.id != item_id]
        elif kind == "feature":
            stories = {s.id for s in b.stories if s.feature_id == item_id}
            b.tasks = [t for t in b.tasks if t.story_id not in stories]
            b.stories = [s for s in b.stories if s.id not in stories]
            b.features = [f for f in b.features if f.id != item_id]
        elif kind == "story":
            b.tasks = [t for t in b.tasks if t.story_id != item_id]
            b.stories = [s for s in b.stories if s.id != item_id]
        else:
            b.tasks = [t for t in b.tasks if t.id != item_id]
        self.save(b)
