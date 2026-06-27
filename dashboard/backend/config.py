"""Shared config resolution so the web API and the agent CLI behave identically.

Both the FastAPI app and the CLI resolve the board file and the ~/.claude location the
same way — via env vars — so an agent driving the CLI and a human on the dashboard see
one source of truth (and tests can redirect both safely).
"""
from __future__ import annotations

import os
from pathlib import Path

from . import telemetry
from .board import BoardStore

_DATA = Path(__file__).resolve().parent.parent / "data"


def claude_dir() -> Path:
    p = os.environ.get("FENRIR_DASH_CLAUDE_DIR")
    return Path(p) if p else telemetry.default_claude_dir()


def board_path(project: str | None = None) -> Path:
    """The board is per-project: data/boards/<slug>.json. `project` wins; else the current
    repo's project is auto-detected; else 'default'. So the kanban is scoped to a project."""
    slug = project or telemetry.current_project_slug(claude_dir()) or "default"
    return _DATA / "boards" / f"{slug}.json"


def store(project: str | None = None) -> BoardStore:
    p = os.environ.get("FENRIR_DASH_BOARD")  # explicit override (tests / pinning) wins
    return BoardStore(Path(p) if p else board_path(project))
