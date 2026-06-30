"""Shared config resolution so the web API and the agent CLI behave identically.

Both the FastAPI app and the CLI resolve the board file and the ~/.claude location the
same way — via env vars — so an agent driving the CLI and a human on the dashboard see
one source of truth (and tests can redirect both safely).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import telemetry
from .board import BoardStore

_DATA = Path(__file__).resolve().parent.parent / "data"

# Load dashboard/.env if present so env knobs (FENRIR_DASH_SINCE, _PROJECT, …) persist across
# restarts for both the web app and the CLI without exporting them by hand. Skipped under pytest
# so a developer's local floor never leaks into the test fixtures' dated events. Best-effort.
if "pytest" not in sys.modules:
    try:
        from dotenv import load_dotenv

        load_dotenv(_DATA.parent / ".env")
    except Exception:  # python-dotenv absent → env-only, no crash
        pass


def claude_dir() -> Path:
    p = os.environ.get("FENRIR_DASH_CLAUDE_DIR")
    return Path(p) if p else telemetry.default_claude_dir()


def board_path(project: str | None = None) -> Path:
    """The board is per-project: data/boards/<slug>.json. `project` wins; else the current
    repo's project is auto-detected; else 'default'. So the kanban is scoped to a project.

    Auto-detection goes through `telemetry.current_project_slug`, which keys off
    `CLAUDE_PROJECT_DIR` (the in-session / launcher-exported repo root) when set, else the real
    cwd — so the bundled-backend launcher (cwd=<plugin>/dashboard) still resolves the USER's repo
    board, matching what scripts/track_session.py (the writer) computes. `FENRIR_DASH_BOARD` in
    `store()` overrides this outright when an exact file is pinned."""
    slug = project or telemetry.current_project_slug(claude_dir()) or "default"
    return _DATA / "boards" / f"{slug}.json"


def retro_dir() -> Path | None:
    """Where epic retrospectives are auto-written on close. `FENRIR_RETRO_DIR` wins; else the
    in-session repo root (`CLAUDE_PROJECT_DIR`) → docs/delivery-memory/retros. None when neither
    is known (e.g. the long-running web server outside a repo) → auto-write disabled there."""
    d = os.environ.get("FENRIR_RETRO_DIR")
    if d:
        return Path(d)
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(root) / "docs" / "delivery-memory" / "retros" if root else None


def store(project: str | None = None) -> BoardStore:
    p = os.environ.get("FENRIR_DASH_BOARD")  # explicit override (tests / pinning) wins
    return BoardStore(Path(p) if p else board_path(project), retro_dir=retro_dir())
