"""Agile board domain model: Epic → Feature → User Story → Task.

Pydantic v2. Statuses follow a standard DevOps flow. Every item carries an optional
`assignee` (an agent name, e.g. `architect`, `coder`, `reviewer`) and a `work_log` of
real telemetry entries (tokens/cost/duration consumed while working it) so the board
cross-links to actual agent activity.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Status(StrEnum):
    backlog = "backlog"
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    done = "done"
    blocked = "blocked"


# Columns shown on the kanban, in order.
KANBAN_COLUMNS: list[Status] = [
    Status.backlog,
    Status.todo,
    Status.in_progress,
    Status.review,
    Status.done,
]


class WorkLogEntry(BaseModel):
    """A unit of real agent work charged against an item (sourced from telemetry)."""

    agent: str = ""
    subagent_type: str = ""  # named subagent (e.g. fenrir:reviewer) when known
    session_id: str = ""
    run_id: str = ""  # subagent run id (agent-<id>) for per-run attribution + idempotency
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    source: str = ""  # manual | telemetry-link | telemetry-run
    note: str = ""
    at: str = ""  # ISO timestamp, supplied by caller (no clock in pure model)


class Transition(BaseModel):
    """A timestamped status change — the basis for flow metrics (cycle time, WIP age)."""

    from_status: str = ""
    to_status: str = ""
    at: str = ""  # ISO timestamp, supplied by caller (no clock in pure model)


class Epic(BaseModel):
    id: str
    title: str
    description: str = ""
    status: Status = Status.backlog
    color: str = "#6366f1"
    created: str = ""
    transitions: list[Transition] = Field(default_factory=list)


class Feature(BaseModel):
    id: str
    epic_id: str
    title: str
    description: str = ""
    status: Status = Status.backlog
    transitions: list[Transition] = Field(default_factory=list)


class UserStory(BaseModel):
    id: str
    feature_id: str
    title: str
    status: Status = Status.backlog
    assignee: str = ""  # agent name
    points: int = 0
    # Classic US phrasing — optional but encouraged.
    as_a: str = ""
    i_want: str = ""
    so_that: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    work_log: list[WorkLogEntry] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    story_id: str
    title: str
    status: Status = Status.backlog
    assignee: str = ""
    work_log: list[WorkLogEntry] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)


class Board(BaseModel):
    epics: list[Epic] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    stories: list[UserStory] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
