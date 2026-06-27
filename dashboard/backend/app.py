"""FastAPI app: serves the SPA, the Agile board CRUD API, and telemetry aggregations.

Run:  uvicorn backend.app:app --reload   (from dashboard/)
Env:  FENRIR_DASH_BOARD       path to board.json (default data/board.json)
      FENRIR_DASH_CLAUDE_DIR  ~/.claude override
      FENRIR_DASH_PROJECT     restrict telemetry to one projects/<name> dir (default: all)
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import telemetry
from .board import BoardStore
from .models import Status, WorkLogEntry

KINDS = {"epic", "feature", "story", "task"}

app = FastAPI(title="Fenrir Dashboard", version="0.1.0")


def _store() -> BoardStore:
    p = os.environ.get("FENRIR_DASH_BOARD")
    return BoardStore(Path(p) if p else None)


def _claude_dir() -> Path:
    p = os.environ.get("FENRIR_DASH_CLAUDE_DIR")
    return Path(p) if p else telemetry.default_claude_dir()


def _events() -> list[dict]:
    return telemetry.load_events(_claude_dir(), os.environ.get("FENRIR_DASH_PROJECT"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise HTTPException(400, f"unknown kind {kind!r} (one of {sorted(KINDS)})")


# --- request bodies -------------------------------------------------------------------
class EpicIn(BaseModel):
    title: str
    description: str = ""
    color: str = "#6366f1"


class FeatureIn(BaseModel):
    epic_id: str
    title: str
    description: str = ""


class StoryIn(BaseModel):
    feature_id: str
    title: str
    assignee: str = ""
    points: int = 0
    as_a: str = ""
    i_want: str = ""
    so_that: str = ""
    acceptance_criteria: list[str] = []


class TaskIn(BaseModel):
    story_id: str
    title: str
    assignee: str = ""


class StatusIn(BaseModel):
    status: Status


class AssignIn(BaseModel):
    assignee: str


# --- API ------------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/board")
def get_board() -> dict:
    return _store().load().model_dump()


@app.post("/api/epics")
def add_epic(body: EpicIn) -> dict:
    return _store().add_epic(body.title, body.description, body.color, _now()).model_dump()


@app.post("/api/features")
def add_feature(body: FeatureIn) -> dict:
    try:
        return _store().add_feature(body.epic_id, body.title, body.description).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/stories")
def add_story(body: StoryIn) -> dict:
    try:
        return _store().add_story(
            body.feature_id, body.title, body.assignee, body.points,
            body.as_a, body.i_want, body.so_that, body.acceptance_criteria,
        ).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/tasks")
def add_task(body: TaskIn) -> dict:
    try:
        return _store().add_task(body.story_id, body.title, body.assignee).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.patch("/api/{kind}/{item_id}/status")
def set_status(kind: str, item_id: str, body: StatusIn) -> dict:
    _check_kind(kind)
    try:
        return _store().set_status(kind, item_id, body.status).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.patch("/api/{kind}/{item_id}/assign")
def assign(kind: str, item_id: str, body: AssignIn) -> dict:
    _check_kind(kind)
    try:
        return _store().assign(kind, item_id, body.assignee).model_dump()
    except (KeyError, ValueError) as e:
        raise HTTPException(404 if isinstance(e, KeyError) else 400, str(e)) from e


@app.post("/api/{kind}/{item_id}/worklog")
def log_work(kind: str, item_id: str, entry: WorkLogEntry) -> dict:
    _check_kind(kind)
    try:
        return _store().log_work(kind, item_id, entry).model_dump()
    except (KeyError, ValueError) as e:
        raise HTTPException(404 if isinstance(e, KeyError) else 400, str(e)) from e


@app.delete("/api/{kind}/{item_id}")
def delete(kind: str, item_id: str) -> dict:
    _check_kind(kind)
    try:
        _store().delete(kind, item_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"deleted": item_id}


@app.get("/api/telemetry/summary")
def telemetry_summary() -> dict:
    return telemetry.summary(_events())


@app.get("/api/telemetry/by-model")
def telemetry_by_model() -> list[dict]:
    return telemetry.by_model(_events())


@app.get("/api/telemetry/by-skill")
def telemetry_by_skill() -> list[dict]:
    return telemetry.by_skill(_events())


@app.get("/api/telemetry/by-day")
def telemetry_by_day() -> list[dict]:
    return telemetry.by_day(_events())


@app.get("/api/telemetry/agents")
def telemetry_agents() -> dict:
    return telemetry.agents(_events())


# --- static SPA (mounted last so /api/* wins) -----------------------------------------
_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="spa")
