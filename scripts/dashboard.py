#!/usr/bin/env python3
"""fenrir — one-command dashboard launcher (pure stdlib, cross-OS).

Starts the BUNDLED dashboard backend that ships inside the plugin, scoped to the
consuming repo's board + telemetry, WITHOUT copying any dashboard code into that repo.

How it stays no-copy + repo-scoped:
  • The dashboard backend MUST run with cwd = the plugin's dashboard dir (so `backend.app`
    imports), but that dir's git root is the PLUGIN, not the user's repo. So the backend can
    NOT key project/board detection off the process cwd here — it would load the plugin's own
    board. Instead the backend's resolver (telemetry.resolution_base) keys off CLAUDE_PROJECT_DIR
    when set, and we export it = the user's repo. Belt-and-suspenders, we ALSO compute the user
    repo's board file via that same resolver and export it as FENRIR_DASH_BOARD, so resolution is
    unambiguous (an explicit --board still wins over the computed one).

Resolution discipline mirrors hooks/run-python.sh + scripts/track_session._dash_python:
  interpreter — prefer the dashboard's own venv (.venv/bin/python POSIX,
  .venv/Scripts/python.exe Windows), else probe python3 → python → py -3 on PATH,
  else the current sys.executable.

Port (highest wins): --port flag → FENRIR_DASH_PORT env → 8765. If the chosen port is
busy, probe upward (+1..+20) and print the real bound URL. 8765 is off the common dev
defaults (8000/8080/3000/5000/8888/9000), so it rarely collides.

FAIL-OPEN by contract: if the bundled dashboard/backend is absent, print a clear skip
line and exit 0 (mirrors the fail-open hooks) — never crash a /command. The one hard
failure is missing FastAPI/uvicorn in the venv (the API genuinely needs them): we print
a one-line `uv sync` hint and exit non-zero.

Flags:  --repo PATH   --port N   --board PATH   --claude-dir PATH   --no-browser

Pure stdlib.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

DEFAULT_PORT = 8765
PORT_PROBE_SPAN = 20  # try <port>..<port>+20 if the preferred one is busy


# --------------------------------------------------------------------------- paths
def _plugin_root() -> Path:
    """The plugin install root. CLAUDE_PLUGIN_ROOT when set (the normal path), else the
    parent of scripts/ (this file lives at <root>/scripts/dashboard.py)."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def _dash_dir() -> Path | None:
    """Locate the bundled dashboard. FENRIR_DASH_DIR override, else <plugin_root>/dashboard.
    None → fail-open skip (mirrors the hooks)."""
    env = os.environ.get("FENRIR_DASH_DIR")
    if env and os.path.isdir(os.path.join(env, "backend")):
        return Path(env).resolve()
    cand = _plugin_root() / "dashboard"
    return cand if (cand / "backend").is_dir() else None


def _dash_python(dash: Path) -> str:
    """Prefer the dashboard's own venv (POSIX `.venv/bin/python` or Windows
    `.venv/Scripts/python.exe`); else probe python3 → python → py -3 on PATH; else the
    current interpreter. Mirrors track_session._dash_python + hooks/run-python.sh."""
    for parts in (("bin", "python"), ("Scripts", "python.exe")):
        venv = dash / ".venv" / Path(*parts)
        if venv.is_file():  # isfile, not exists: a dir named `python` must not be returned
            return str(venv)
    for cand in ("python3", "python"):
        found = shutil.which(cand)
        if found:
            return found
    if shutil.which("py"):  # Windows python.org launcher
        return "py"
    return sys.executable


def _resolve_board(dash: Path, interp: str, repo: str) -> str | None:
    """Ask the bundled backend's OWN resolver for the board file of `repo`, so the launcher
    exports exactly what the reader (config.board_path) and writer (scripts/track_session) would
    compute — no path logic duplicated here. Runs with cwd=dash + CLAUDE_PROJECT_DIR=repo, the
    same conditions the backend will see. Best-effort: None on any failure (the exported
    CLAUDE_PROJECT_DIR alone already scopes resolution; this is the belt-and-suspenders half)."""
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = repo
    env.pop("FENRIR_DASH_BOARD", None)  # don't let a stray pin echo back as the "computed" path
    try:
        r = subprocess.run(
            [interp, "-c", "from backend import config; print(config.board_path())"],
            cwd=str(dash), env=env, capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    out = (r.stdout or "").strip()
    return out or None


# --------------------------------------------------------------------------- port
def _port_is_free(port: int) -> bool:
    """True if 127.0.0.1:<port> is bindable right now (best-effort race-prone probe)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _pick_port(preferred: int) -> int | None:
    """First free port in [preferred, preferred+PORT_PROBE_SPAN]. None if all busy."""
    for port in range(preferred, preferred + PORT_PROBE_SPAN + 1):
        if _port_is_free(port):
            return port
    return None


def _resolve_preferred_port(arg_port: int | None) -> int:
    """--port flag → FENRIR_DASH_PORT env → DEFAULT_PORT (8765)."""
    if arg_port is not None:
        return arg_port
    env = os.environ.get("FENRIR_DASH_PORT")
    if env:
        try:
            return int(env)
        except ValueError:
            print(f"[fenrir:dashboard] ignoring non-integer FENRIR_DASH_PORT={env!r}", file=sys.stderr)
    return DEFAULT_PORT


# --------------------------------------------------------------------------- browser
def _open_browser_later(url: str, delay: float = 1.2) -> None:
    """Open the browser after a short delay so the server has a moment to bind. Best-effort
    in a daemon thread; a headless/sandboxed host that can't open a browser is non-fatal."""
    def _go() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


# --------------------------------------------------------------------------- main
def _skip(reason: str) -> int:
    print(f"[fenrir:dashboard] skipped — {reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="fenrir-dashboard",
        description="Launch the bundled Fenrir dashboard scoped to a repo (no code copied).",
    )
    p.add_argument("--repo", default="", help="Repo to scope the board/telemetry to "
                   "(default: CLAUDE_PROJECT_DIR or the current directory).")
    p.add_argument("--port", type=int, default=None, help="Bind port "
                   f"(default: FENRIR_DASH_PORT or {DEFAULT_PORT}; auto-increments if busy).")
    p.add_argument("--board", default="", help="Explicit board JSON path "
                   "(exported as FENRIR_DASH_BOARD; overrides the per-project default).")
    p.add_argument("--claude-dir", default="", help="Override ~/.claude scanned for telemetry "
                   "(exported as FENRIR_DASH_CLAUDE_DIR).")
    p.add_argument("--no-browser", action="store_true", help="Do not open a web browser.")
    a = p.parse_args(argv)

    dash = _dash_dir()
    if dash is None:
        return _skip("bundled dashboard not found (set CLAUDE_PLUGIN_ROOT or FENRIR_DASH_DIR). "
                     "Tracking/board still work via the hooks; only the web UI is unavailable.")

    # Resolve the consuming repo BEFORE anything chdir-y. Default to CLAUDE_PROJECT_DIR,
    # else the cwd we were launched from — that git root is what the board/telemetry key off.
    repo = a.repo or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    repo = str(Path(repo).resolve())

    interp = _dash_python(dash)

    # Child env: the backend runs with cwd=dash but must resolve the USER's project, so we
    # pass the repo through CLAUDE_PROJECT_DIR. --board / --claude-dir pin the existing envs
    # the backend already honors (and which always win over the cwd-derived defaults).
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = repo
    if a.claude_dir:
        env["FENRIR_DASH_CLAUDE_DIR"] = str(Path(a.claude_dir).resolve())
    if a.board:  # explicit pin wins outright
        env["FENRIR_DASH_BOARD"] = str(Path(a.board).resolve())
    else:
        # Belt-and-suspenders: compute the USER repo's board via the backend's own resolver and
        # pin it, so the board loaded is unambiguous even if cwd-based detection would differ.
        board = _resolve_board(dash, interp, repo)
        if board:
            env["FENRIR_DASH_BOARD"] = board

    preferred = _resolve_preferred_port(a.port)
    port = _pick_port(preferred)
    if port is None:
        return _skip(f"no free port in [{preferred}, {preferred + PORT_PROBE_SPAN}] — "
                     "pass --port / FENRIR_DASH_PORT to choose another.")
    if port != preferred:
        print(f"[fenrir:dashboard] port {preferred} busy → using {port}")

    url = f"http://127.0.0.1:{port}"
    print(f"[fenrir:dashboard] serving the bundled dashboard for {repo}")
    print(f"[fenrir:dashboard] open {url}  (Ctrl-C to stop)")

    if not a.no_browser:
        _open_browser_later(url)

    cmd = [interp, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(port)]
    try:
        proc = subprocess.run(cmd, cwd=str(dash), env=env)
    except FileNotFoundError:
        # interpreter vanished between probe and spawn — unusual; treat as fail-open skip
        return _skip(f"interpreter {interp!r} not runnable")
    except KeyboardInterrupt:
        return 0

    rc = proc.returncode
    if rc != 0:
        # The most common real failure: FastAPI/uvicorn not installed in the dashboard venv.
        print("[fenrir:dashboard] backend exited non-zero. If this is a fresh checkout, the "
              "dashboard deps may be missing — install them once with:", file=sys.stderr)
        print(f"    cd \"{dash}\" && uv sync --extra dev", file=sys.stderr)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
