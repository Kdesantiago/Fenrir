"""FastAPI app: serves the SPA, the Agile board CRUD API, and telemetry aggregations.

Run:  uvicorn backend.app:app --port 8765 --reload   (from dashboard/)
      or, from any repo:  /fenrir:dashboard  (the plugin launcher, no copy needed)
Env:  FENRIR_DASH_PORT        bind port for the launcher / docs (default 8765; uvicorn's
                              own default is still 8000 if you omit --port)
      FENRIR_DASH_BOARD       path to a board JSON file (pins it outright; overrides the
                              per-project default)
      FENRIR_DASH_CLAUDE_DIR  ~/.claude override
      FENRIR_DASH_PROJECT     restrict telemetry to one projects/<name> dir (default: all)
      CLAUDE_PROJECT_DIR      the in-session repo root. When set, project/board auto-detection
                              keys off THIS path (its git root) instead of the process cwd — so
                              the bundled-backend launcher, which runs with cwd=<plugin>/dashboard,
                              still resolves the USER repo's board/telemetry. See config.board_path
                              + telemetry.resolution_base.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import catalog as catalog_mod
from . import config, telemetry
from .models import Status, WorkLogEntry

KINDS = {"epic", "feature", "story", "task"}

app = FastAPI(title="Fenrir Dashboard", version="0.1.0")


def _store(project: str | None = None):
    return config.store(_resolve_project(project) if project is not None else None)


def _claude_dir() -> Path:
    return config.claude_dir()


def _resolve_project(q: str | None) -> str | None:
    """Which project to scope telemetry to. Query param wins; then the FENRIR_DASH_PROJECT env;
    then auto-detect the current repo's project (via `current_project_slug`, which keys off
    CLAUDE_PROJECT_DIR when the launcher set it, else the cwd — so the bundled backend scopes to
    the USER's repo). `""`/`"all"` means every project."""
    if q is None:
        env = os.environ.get("FENRIR_DASH_PROJECT")
        if env is not None:
            return env or None
        return telemetry.current_project_slug(_claude_dir())
    return None if q in ("", "all") else q


def _events(project: str | None) -> list[dict]:
    return telemetry.load_events(_claude_dir(), _resolve_project(project))


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
def get_board(project: str | None = None) -> dict:
    return _store(project).load().model_dump()


@app.get("/api/board/costs")
def board_costs(project: str | None = None) -> dict:
    return _store(project).costs()


@app.get("/api/board/flow")
def board_flow(project: str | None = None) -> dict:
    """Flow metrics: cycle time, weekly throughput, current WIP + aging, Monte-Carlo forecast."""
    return _store(project).flow_metrics(now=_now())


@app.get("/api/board/audit")
def board_audit(project: str | None = None, coarse_usd: float = 50.0, dominance: float = 0.4) -> dict:
    """Agile hygiene: flag US that aren't atomic (umbrellas) + structural smells."""
    return _store(project).audit(coarse_usd=coarse_usd, dominance=dominance)


@app.get("/api/trace")
def trace(us: str | None = None, feature: str | None = None, epic: str | None = None,
          newest_first: bool = True, project: str | None = None) -> list[dict]:
    return _store(project).trace(us or None, feature or None, epic or None, newest_first)


@app.post("/api/epics")
def add_epic(body: EpicIn, project: str | None = None) -> dict:
    return _store(project).add_epic(body.title, body.description, body.color, _now()).model_dump()


@app.post("/api/features")
def add_feature(body: FeatureIn, project: str | None = None) -> dict:
    try:
        return _store(project).add_feature(body.epic_id, body.title, body.description).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/stories")
def add_story(body: StoryIn, project: str | None = None) -> dict:
    try:
        return _store(project).add_story(
            body.feature_id, body.title, body.assignee, body.points,
            body.as_a, body.i_want, body.so_that, body.acceptance_criteria,
        ).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/tasks")
def add_task(body: TaskIn, project: str | None = None) -> dict:
    try:
        return _store(project).add_task(body.story_id, body.title, body.assignee).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.patch("/api/{kind}/{item_id}/status")
def set_status(kind: str, item_id: str, body: StatusIn, project: str | None = None) -> dict:
    _check_kind(kind)
    try:
        return _store(project).set_status(kind, item_id, body.status, at=_now()).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.patch("/api/{kind}/{item_id}/assign")
def assign(kind: str, item_id: str, body: AssignIn, project: str | None = None) -> dict:
    _check_kind(kind)
    try:
        return _store(project).assign(kind, item_id, body.assignee).model_dump()
    except (KeyError, ValueError) as e:
        raise HTTPException(404 if isinstance(e, KeyError) else 400, str(e)) from e


@app.post("/api/{kind}/{item_id}/worklog")
def log_work(kind: str, item_id: str, entry: WorkLogEntry, project: str | None = None) -> dict:
    _check_kind(kind)
    try:
        return _store(project).log_work(kind, item_id, entry).model_dump()
    except (KeyError, ValueError) as e:
        raise HTTPException(404 if isinstance(e, KeyError) else 400, str(e)) from e


@app.delete("/api/{kind}/{item_id}")
def delete(kind: str, item_id: str, project: str | None = None) -> dict:
    _check_kind(kind)
    try:
        _store(project).delete(kind, item_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"deleted": item_id}


@app.get("/api/projects")
def projects() -> dict:
    cd = _claude_dir()
    return {"active": telemetry.current_project_slug(cd), "projects": telemetry.list_projects(cd)}


@app.get("/api/telemetry/summary")
def telemetry_summary(project: str | None = None) -> dict:
    out = telemetry.summary(_events(project))
    out["scope"] = _resolve_project(project) or "all projects"
    out["since"] = os.environ.get("FENRIR_DASH_SINCE") or None
    return out


@app.get("/api/telemetry/by-model")
def telemetry_by_model(project: str | None = None) -> list[dict]:
    return telemetry.by_model(_events(project))


@app.get("/api/telemetry/by-skill")
def telemetry_by_skill(project: str | None = None) -> list[dict]:
    return telemetry.by_skill(_events(project))


@app.get("/api/telemetry/by-day")
def telemetry_by_day(project: str | None = None) -> list[dict]:
    return telemetry.by_day(_events(project))


@app.get("/api/telemetry/agents")
def telemetry_agents(project: str | None = None) -> dict:
    return telemetry.agents(_events(project))


@app.get("/api/telemetry/efficiency")
def telemetry_efficiency(project: str | None = None) -> dict:
    """Cache efficiency: actual vs uncached-equivalent cost, savings, hit-ratio per model."""
    return telemetry.efficiency(_events(project))


@app.get("/api/telemetry/subagents")
def telemetry_subagents(project: str | None = None) -> dict:
    return telemetry.subagent_runs(_claude_dir(), _resolve_project(project))


@app.get("/api/catalog")
def catalog() -> dict:
    """Self-documenting reference: every agent / hook / skill / command + its description (read
    from the plugin's own files on disk), so the pack is understandable with zero code reading."""
    return catalog_mod.catalog()


# --- static SPA (mounted last so /api/* wins) -----------------------------------------
_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="spa")
