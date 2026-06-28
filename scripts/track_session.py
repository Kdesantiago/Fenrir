#!/usr/bin/env python3
"""fenrir — deterministic delivery-tracking engine.

The guaranteed half of "automatic + mandatory" board tracking. Hooks call this; it never
needs the model. It reads the dashboard board (read-only, to look up ids) and MUTATES only
through the board CLI (`python -m backend.cli ...`) so there is one source of truth.

It is the floor, not the ceiling: it guarantees *something* is tracked (a catch-all
Epic → Feature(branch) → US(session)) and that the session's real cost is attributed.
The `delivery-tracker` SUBAGENT does the smart part (good titles, correct Epic/Feature
placement, per-run splitting when a session spans several US).

FAIL-OPEN by contract: no dashboard, no board, broken CLI → print a skip line, exit 0.
Tracking must never block delivery by accident. The only place that can DENY is the guard,
and only in opt-in strict mode (see tracking-guard.py).

Commands
  ensure-us   --session ID [--summary TXT] [--branch B]   -> ensure an active US exists; print it
  collect-run --session ID --run RUN_ID [--type T]        -> ledger a finished subagent run
  finalize    --session ID [--summary TXT]                -> ensure-us + attribute real cost
  check       --session ID                                -> exit 0 if the session is traced, 3 if not
  status      [--session ID]                              -> print the current tracking state (JSON)

Pure stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime

CATCHALL_EPIC = "Auto-tracked sessions"
STATE_DIRNAME = os.path.join(".claude", "tracking")


# --------------------------------------------------------------------------- paths
def _root() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _dash_dir() -> str | None:
    """Locate the dashboard companion app. None → tracking is a no-op (fail-open)."""
    d = os.environ.get("FENRIR_DASH_DIR")
    if d and os.path.isdir(d):
        return d
    cand = os.path.join(_root(), "dashboard")
    return cand if os.path.isdir(os.path.join(cand, "backend")) else None


def _dash_python(dash: str) -> str:
    """Prefer the dashboard's own venv; fall back to the current interpreter."""
    venv = os.path.join(dash, ".venv", "bin", "python")
    return venv if os.path.exists(venv) else sys.executable


def _board_path(dash: str) -> str:
    """Resolve the board file EXACTLY as the dashboard does — the board is per-project
    (data/boards/<slug>.json), so reading the legacy data/board.json would miss everything
    and cause duplicate US creation. Ask the dashboard's own config resolver."""
    env = os.environ.get("FENRIR_DASH_BOARD")
    if env:
        return env if os.path.isabs(env) else os.path.join(dash, env)
    try:
        r = subprocess.run(
            [_dash_python(dash), "-c", "from backend import config; print(config.board_path())"],
            cwd=dash, capture_output=True, text=True, timeout=15)
        p = (r.stdout or "").strip()
        if p:
            return p
    except Exception:
        pass
    return os.path.join(dash, "data", "board.json")  # legacy fallback


def _state_dir() -> str:
    d = os.path.join(_root(), STATE_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def _active_path() -> str:
    return os.path.join(_state_dir(), "active.json")


def _runs_path(session: str) -> str:
    safe = "".join(c for c in session if c.isalnum() or c in "-_") or "session"
    return os.path.join(_state_dir(), f"{safe}.runs.jsonl")


# --------------------------------------------------------------------------- git
def _branch() -> str:
    for args in (["git", "symbolic-ref", "--short", "HEAD"],
                 ["git", "rev-parse", "--abbrev-ref", "HEAD"]):
        try:
            r = subprocess.run(args, cwd=_root(), capture_output=True, text=True, timeout=2)
            out = r.stdout.strip()
            if r.returncode == 0 and out and out != "HEAD":
                return out
        except Exception:
            pass
    return "detached"


# --------------------------------------------------------------------------- board CLI
def _cli(dash: str, *cli_args: str) -> dict:
    """Run a board CLI command, return its parsed JSON object ({} on any trouble)."""
    try:
        r = subprocess.run(
            [_dash_python(dash), "-m", "backend.cli", *cli_args],
            cwd=dash, capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return {}
    out = (r.stdout or "").strip()
    if not out:
        return {}
    # the CLI prints one JSON object on success (indent=2, so multi-line).
    try:
        obj = json.loads(out)
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, ValueError):
        pass
    # fallback: extract the last balanced {...} block from mixed output
    start = out.find("{")
    end = out.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(out[start:end + 1])
            return obj if isinstance(obj, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _load_board(dash: str) -> dict:
    try:
        with open(_board_path(dash)) as f:
            return json.load(f)
    except Exception:
        return {}


def _find_epic(board: dict, title: str) -> str:
    for e in board.get("epics", []):
        if e.get("title") == title:
            return e.get("id", "")
    return ""


def _find_feature(board: dict, epic_id: str, title: str) -> str:
    for fe in board.get("features", []):
        if fe.get("epic_id") == epic_id and fe.get("title") == title:
            return fe.get("id", "")
    return ""


def _story_for_session(board: dict, session: str) -> str:
    """A US already carries this session in its work_log → reuse it (idempotency)."""
    for st in board.get("stories", []):
        for w in st.get("work_log", []):
            if w.get("session_id") == session:
                return st.get("id", "")
    return ""


# --------------------------------------------------------------------------- state
def _read_active() -> dict:
    try:
        with open(_active_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_active(d: dict) -> None:
    try:
        with open(_active_path(), "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def _skip(reason: str) -> int:
    print(json.dumps({"tracking": "skipped", "reason": reason}))
    return 0


# --------------------------------------------------------------------------- commands
def cmd_ensure_us(a) -> int:
    dash = _dash_dir()
    if not dash:
        return _skip("no dashboard companion app (tracking disabled)")
    session = a.session or _read_active().get("session_id", "")
    if not session:
        return _skip("no session id")

    # already active for this session?
    active = _read_active()
    if active.get("session_id") == session and active.get("us_id"):
        print(json.dumps({"tracking": "active", "us_id": active["us_id"], "session_id": session}))
        return 0

    board = _load_board(dash)
    # idempotency: a US may already own this session from a prior run
    us = _story_for_session(board, session)
    if not us:
        branch = a.branch or _branch()
        epic = _find_epic(board, CATCHALL_EPIC)
        if not epic:
            epic = _cli(dash, "epic", "add", "--title", CATCHALL_EPIC,
                        "--description", "Sessions auto-tracked by the delivery-tracking hooks. "
                        "Re-parent / rename via the delivery-tracker subagent.",
                        "--color", "#64748b").get("id", "")
            board = _load_board(dash)
        feat = _find_feature(board, epic, branch) if epic else ""
        if epic and not feat:
            feat = _cli(dash, "feature", "add", "--epic", epic, "--title", branch,
                        "--description", f"Auto-tracked work on branch `{branch}`.").get("id", "")
        if not feat:
            return _skip("could not create catch-all feature (board CLI unavailable)")
        summary = (a.summary or "").strip()
        title = f"{branch} — {date.today().isoformat()}"
        if summary:
            title += f" — {summary[:80]}"
        us = _cli(dash, "story", "add", "--feature", feat, "--title", title,
                  "--assignee", "coder", "--so-that", "the work is traced").get("id", "")
    if not us:
        return _skip("could not create user story (board CLI unavailable)")

    _write_active({"session_id": session, "us_id": us, "branch": a.branch or _branch(),
                   "at": datetime.now().astimezone().isoformat()})
    print(json.dumps({"tracking": "ensured", "us_id": us, "session_id": session}))
    return 0


def cmd_set_us(a) -> int:
    """Steer the ACTIVE User Story for a session, so subagent runs attribute to it live.
    Lets an orchestrator (/deliver, the main thread) scope cost per-US within one session."""
    if not a.id:
        return _skip("set-us needs --id")
    dash = _dash_dir()
    session = a.session or _read_active().get("session_id", "")
    if dash:  # validate the US exists when we can
        ids = {s.get("id") for s in _load_board(dash).get("stories", [])}
        if ids and a.id not in ids:
            return _skip(f"US {a.id} not on the board")
    cur = _read_active()
    cur.update({"session_id": session, "us_id": a.id,
                "at": datetime.now().astimezone().isoformat()})
    _write_active(cur)
    print(json.dumps({"tracking": "active-us-set", "us_id": a.id, "session_id": session}))
    return 0


def cmd_collect_run(a) -> int:
    if not a.session or not a.run:
        return _skip("collect-run needs --session and --run")
    try:
        with open(_runs_path(a.session), "a") as f:
            f.write(json.dumps({"run": a.run, "type": a.type or "",
                                "at": datetime.now().astimezone().isoformat()}) + "\n")
    except Exception as e:
        return _skip(f"ledger write failed: {e}")
    # LIVE per-run attribution: if a US is active for this session, charge THIS run to it now
    # (precise per-US cost, automatically). Mutually exclusive with whole-session link — once
    # any run is attributed, finalize's link is refused by the CLI and skipped gracefully.
    attributed = None
    dash = _dash_dir()
    active = _read_active()
    us = active.get("us_id", "") if active.get("session_id") == a.session else ""
    if dash and us:
        res = _cli(dash, "attribute", "--kind", "story", "--id", us, "--run", a.run,
                   "--note", f"auto: {a.type or 'subagent'} run")
        if res:
            attributed = us
    print(json.dumps({"tracking": "collected", "run": a.run, "session_id": a.session,
                      "attributed_to": attributed}))
    return 0


def cmd_finalize(a) -> int:
    dash = _dash_dir()
    if not dash:
        return _skip("no dashboard companion app (tracking disabled)")
    session = a.session or _read_active().get("session_id", "")
    if not session:
        return _skip("no session id")

    # make sure a US exists, then charge the session's real cost to it.
    cmd_ensure_us(a)  # idempotent; prints its own line
    us = _read_active().get("us_id", "") or _story_for_session(_load_board(dash), session)
    if not us:
        return _skip("no active US to attribute to")

    # whole-session link (coarse, captures main + subagent), REFRESHED each call so cost stays
    # current turn-by-turn. If the session was already split per-run by the subagent, the CLI
    # refuses link → we skip gracefully.
    res = _cli(dash, "link", "--kind", "story", "--id", us, "--session", session,
               "--refresh", "--note", "auto-tracked (live)")
    print(json.dumps({"tracking": "finalized", "us_id": us, "session_id": session,
                      "link_result": res or "skipped (already attributed / CLI unavailable)"}))
    return 0


def cmd_check(a) -> int:
    """Exit 0 if traced, 3 if not. Used by the guard. Fail-open (0) when no dashboard."""
    dash = _dash_dir()
    if not dash:
        print(json.dumps({"tracking": "untracked-ok", "reason": "no dashboard"}))
        return 0
    session = a.session or _read_active().get("session_id", "")
    active = _read_active()
    if active.get("session_id") == session and active.get("us_id"):
        print(json.dumps({"tracking": "traced", "us_id": active["us_id"]}))
        return 0
    if session and _story_for_session(_load_board(dash), session):
        return 0
    print(json.dumps({"tracking": "untraced", "session_id": session}))
    return 3


def cmd_status(a) -> int:
    dash = _dash_dir()
    print(json.dumps({
        "dashboard": dash or None,
        "board": _board_path(dash) if dash else None,
        "active": _read_active(),
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="track_session", description="fenrir delivery-tracking engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ensure-us"); a.add_argument("--session", default="")
    a.add_argument("--summary", default=""); a.add_argument("--branch", default="")
    a.set_defaults(fn=cmd_ensure_us)

    a = sub.add_parser("set-us"); a.add_argument("--id", default="")
    a.add_argument("--session", default=""); a.set_defaults(fn=cmd_set_us)

    a = sub.add_parser("collect-run"); a.add_argument("--session", default="")
    a.add_argument("--run", default=""); a.add_argument("--type", default="")
    a.set_defaults(fn=cmd_collect_run)

    a = sub.add_parser("finalize"); a.add_argument("--session", default="")
    a.add_argument("--summary", default=""); a.add_argument("--branch", default="")
    a.set_defaults(fn=cmd_finalize)

    a = sub.add_parser("check"); a.add_argument("--session", default="")
    a.set_defaults(fn=cmd_check)

    a = sub.add_parser("status"); a.add_argument("--session", default="")
    a.set_defaults(fn=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except SystemExit:
        raise
    except Exception as e:  # never break a hook
        return _skip(f"unexpected error: {e}")


if __name__ == "__main__":
    sys.exit(main())
