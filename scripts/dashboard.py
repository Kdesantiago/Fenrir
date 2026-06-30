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

TRULY zero-install: on the first launch from a fresh checkout the dashboard's `.venv` is
gitignored (never shipped), so FastAPI/uvicorn are absent. Rather than print a hint and bail,
the launcher AUTO-RUNS `uv sync` in the dashboard dir to build+populate the venv, then
re-resolves the interpreter to that fresh `.venv` and proceeds. This is idempotent: a normal
launch with deps already present does NOT re-sync (a fast import probe gates it), so warm
launches stay fast. If `uv` itself is absent from PATH we fall back to the old behavior (a
clear "install uv OR run the documented manual step" message) and exit non-zero — never crash.

FAIL-OPEN by contract: if the bundled dashboard/backend is absent, print a clear skip
line and exit 0 (mirrors the fail-open hooks) — never crash a /command.

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


def _dash_venv_python(dash: Path) -> str | None:
    """The dashboard's OWN venv interpreter if it exists (POSIX `.venv/bin/python` or Windows
    `.venv/Scripts/python.exe`), else None. The `.venv` is gitignored, so on a fresh checkout
    this is None — the signal that `uv sync` hasn't run here yet."""
    for parts in (("bin", "python"), ("Scripts", "python.exe")):
        venv = dash / ".venv" / Path(*parts)
        if venv.is_file():  # isfile, not exists: a dir named `python` must not be returned
            return str(venv)
    return None


def _dash_python(dash: Path) -> str:
    """Prefer the dashboard's own venv (POSIX `.venv/bin/python` or Windows
    `.venv/Scripts/python.exe`); else probe python3 → python → py -3 on PATH; else the
    current interpreter. Mirrors track_session._dash_python + hooks/run-python.sh."""
    venv = _dash_venv_python(dash)
    if venv is not None:
        return venv
    for cand in ("python3", "python"):
        found = shutil.which(cand)
        if found:
            return found
    if shutil.which("py"):  # Windows python.org launcher
        return "py"
    return sys.executable


def _deps_present(interp: str) -> bool:
    """True iff `interp` can import BOTH fastapi and uvicorn — the two libs the API genuinely
    needs. A quiet, fast subprocess probe (the import-or-die idiom): this is the idempotency
    guard, so a warm venv answers True in milliseconds and we skip the (slow) `uv sync`."""
    try:
        r = subprocess.run(
            [interp, "-c", "import fastapi, uvicorn"],
            capture_output=True, text=True, timeout=30)
    except Exception:
        return False
    return r.returncode == 0


def _uv_sync(dash: Path) -> bool:
    """Build/populate the dashboard's `.venv` by running `uv sync` (the project standard) with
    cwd=dash, so it resolves dashboard/pyproject.toml + uv.lock into dashboard/.venv. Returns
    True on success. Graceful: if `uv` is absent from PATH we return False WITHOUT raising, so
    the caller can fall back to the documented manual step instead of crashing. Cross-OS — no
    shell, just subprocess; uv itself picks the right `.venv/bin` vs `.venv/Scripts` layout."""
    if not shutil.which("uv"):
        return False
    print("[fenrir:dashboard] first run: installing dashboard deps via uv sync… "
          "(one-time; subsequent launches are fast)")
    try:
        r = subprocess.run(["uv", "sync"], cwd=str(dash))
    except Exception as exc:  # pragma: no cover — uv vanished between which() and spawn
        print(f"[fenrir:dashboard] uv sync could not run: {exc}", file=sys.stderr)
        return False
    return r.returncode == 0


def _ensure_deps(dash: Path, interp: str) -> tuple[str, bool]:
    """Idempotently guarantee the dashboard runs on an interpreter that can import fastapi+uvicorn.

    The dashboard pins `requires-python >=3.11` and uses 3.11+ stdlib (e.g. datetime.UTC), so the
    ONLY interpreter we trust is the dashboard's OWN `.venv` that `uv sync` builds from its
    pyproject + uv.lock — never a stray PATH python that merely happens to carry an (old) fastapi.

    Fast path (warm): the `.venv` exists AND imports the deps → use it, NO `uv sync`. This is the
    idempotency guard, so a normal launch stays fast.

    Cold path: the `.venv` is absent (fresh checkout — it's gitignored) OR present-but-broken →
    run `uv sync` to (re)build it, then resolve to that venv and re-probe.

    Returns (interpreter, ok). ok=False means we still don't have a working venv AND couldn't make
    one (uv absent, or sync failed) — the caller prints the manual fallback and exits non-zero."""
    venv = _dash_venv_python(dash)
    if venv is not None and _deps_present(venv):
        return venv, True  # warm: trusted venv with deps — skip uv sync entirely
    if not _uv_sync(dash):
        return interp, False
    # uv sync just (re)built dashboard/.venv — prefer it explicitly and verify the deps landed.
    fresh = _dash_venv_python(dash) or _dash_python(dash)
    return fresh, _deps_present(fresh)


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

    # Zero-install: ensure the API's deps (fastapi+uvicorn) are importable. If they're missing
    # (fresh checkout → no `.venv` shipped), auto-build it with `uv sync` and re-resolve the
    # interpreter to the fresh venv. Idempotent: a warm venv skips the sync. If we still can't
    # (no `uv` on PATH, or sync failed), fall back to a clear message and exit non-zero.
    interp, deps_ok = _ensure_deps(dash, interp)
    if not deps_ok:
        print("[fenrir:dashboard] the dashboard needs FastAPI + uvicorn and they're not "
              "installed.", file=sys.stderr)
        if not shutil.which("uv"):
            print("    `uv` is not on PATH. Install it (https://docs.astral.sh/uv/) so the "
                  "first launch can auto-install deps, OR install them manually:", file=sys.stderr)
        else:
            print("    `uv sync` did not produce a working venv. Try it manually to see why:",
                  file=sys.stderr)
        print(f"    cd \"{dash}\" && uv sync", file=sys.stderr)
        return 1

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
        # Deps were verified importable before serving (we'd have auto-synced otherwise), so a
        # non-zero here is a genuine runtime/bind error, not a missing-dependency one. Surface
        # the manual run that streams the backend's own traceback.
        print("[fenrir:dashboard] backend exited non-zero. To see the full traceback, run it "
              "directly:", file=sys.stderr)
        print(f"    cd \"{dash}\" && uv run uvicorn backend.app:app --port {port}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
