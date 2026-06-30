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
  ensure-us        --session ID [--summary TXT] [--branch B]  -> ensure an active US exists; print it
  set-us           --id US --session ID                       -> steer the active US (records a uslog point)
  collect-run      --session ID --run RUN_ID [--type T]       -> ledger a finished subagent run
  attribute-commit --session ID [--id US]                     -> at a git commit, flush the cost since the
                                                                 last commit to the US that commit delivers
  focus            --session ID [--trigger T] [--instructions] -> snapshot the current dev subject (active US +
                                                                 git) so a compaction can be re-focused on it
  finalize         --session ID [--summary TXT]               -> ensure-us + attribute real cost
  check            --session ID                               -> exit 0 if the session is traced, 3 if not
  status           [--session ID]                             -> print the current tracking state (JSON)

Pure stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
    """Prefer the dashboard's own venv (POSIX `.venv/bin/python` or Windows
    `.venv/Scripts/python.exe`); fall back to the current interpreter."""
    for parts in (("bin", "python"), ("Scripts", "python.exe")):
        venv = os.path.join(dash, ".venv", *parts)
        if os.path.isfile(venv):  # isfile, not exists: a dir named `python` must not be returned
            return venv
    return sys.executable


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


def _safe(session: str) -> str:
    return "".join(c for c in session if c.isalnum() or c in "-_") or "session"


def _runs_path(session: str) -> str:
    return os.path.join(_state_dir(), f"{_safe(session)}.runs.jsonl")


def _uslog_path(session: str) -> str:
    """Ledger of (at, us) active-US changes — lets reconcile map each run to the US that was
    active when it ran (time-sweep), so per-US cost is correct without relying on SubagentStop."""
    return os.path.join(_state_dir(), f"{_safe(session)}.uslog.jsonl")


def _watermark_path(session: str) -> str:
    return os.path.join(_state_dir(), f"{_safe(session)}.main.json")


def _focus_path() -> str:
    """The compaction-focus snapshot: the current dev subject, written before a compaction so
    the post-compaction session (SessionStart source=compact) can re-seed it. Per-repo, one file."""
    return os.path.join(_state_dir(), "compact-focus.md")


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


def _git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=_root(),
                           capture_output=True, text=True, timeout=4)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


_US_RE = re.compile(r"\bus-\d+\b", re.IGNORECASE)


def _head_commit_us() -> str:
    """The US the HEAD commit declares (first `us-N` in its message), '' if none.
    The delivery-trace gate already pushes work to reference a US, so commits usually carry one."""
    try:
        r = subprocess.run(["git", "log", "-1", "--pretty=%B"],
                           cwd=_root(), capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            m = _US_RE.search(r.stdout or "")
            if m:
                return m.group(0).lower()
    except Exception:
        pass
    return ""


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


def _append_uslog(session: str, us: str) -> None:
    """Record (at, us) so reconcile can map each run to the US active when it ran."""
    if not session or not us:
        return
    try:
        with open(_uslog_path(session), "a") as f:
            f.write(json.dumps({"at": datetime.now().astimezone().isoformat(), "us": us}) + "\n")
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
    _append_uslog(session, us)
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
    _append_uslog(session, a.id)
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
    # Ledger only. Attribution is done by `finalize` (the single authority): it time-sweeps the
    # session's runs and attributes each to the US active WHEN IT RAN. Doing a live attribute here
    # too could pin the same run to a different US than the sweep picks → double-count.
    print(json.dumps({"tracking": "collected", "run": a.run, "session_id": a.session}))
    return 0


def cmd_finalize(a) -> int:
    """Reconcile REAL cost PER-US (the mandatory, automatic path):
      • subagents — attribute each of the session's runs to the US active WHEN IT RAN
        (time-sweep over the set-us ledger; idempotent per run). Robust even if SubagentStop
        never fired for it.
      • main thread — attribute the cost accrued since the last reconcile (a watermark delta)
        to the CURRENTLY active US.
    main and subagent are disjoint telemetry sources, so there is no double-count. Replaces the
    old whole-session link (which could only put everything on ONE US)."""
    dash = _dash_dir()
    if not dash:
        return _skip("no dashboard companion app (tracking disabled)")
    session = a.session or _read_active().get("session_id", "")
    if not session:
        return _skip("no session id")
    cmd_ensure_us(a)  # guarantees an active US (prints its own line)
    current_us = _read_active().get("us_id", "") or _story_for_session(_load_board(dash), session)
    if not current_us:
        return _skip("no active US to attribute to")

    # one in-process pass in the CLI (fast for hundreds of runs): subagents → US active when
    # they ran (time-sweep over the uslog), main-thread → current US as a watermark delta.
    res = _cli(dash, "reconcile", "--session", session, "--current-us", current_us,
               "--uslog", _uslog_path(session), "--watermark", _watermark_path(session))
    print(json.dumps({"tracking": "reconciled", "session_id": session,
                      "current_us": current_us, "result": res or "skipped (CLI unavailable)"}))
    return 0


def cmd_attribute_commit(a) -> int:
    """At a git commit, charge the cost accrued SINCE THE LAST COMMIT to the US that commit
    delivers. The commit is the unit of attribution: "work since the previous commit → THIS
    commit's US". The US is resolved in order: --id, the first `us-N` in the HEAD commit message
    (the delivery-trace gate makes commits reference one), the current active US, else a
    catch-all. It sets that US active (recording a uslog boundary), then reconciles — the
    main-thread watermark delta lands on THIS US, subagent runs on the US active when each ran.
    Idempotent (watermark + per-run keys) and fail-open. This is the half that makes per-US cost
    AUTOMATIC + MANDATORY: it fires on every commit (a PostToolUse hook), no manual step."""
    dash = _dash_dir()
    if not dash:
        return _skip("no dashboard companion app (tracking disabled)")
    session = a.session or _read_active().get("session_id", "")
    if not session:
        return _skip("no session id")
    us = (getattr(a, "id", "") or "").strip().lower() or _head_commit_us()
    if not us:
        us = _read_active().get("us_id", "")
    if not us:  # nothing active and the commit names no US → guarantee a catch-all, then use it
        cmd_ensure_us(a)
        us = _read_active().get("us_id", "")
    if not us:
        return _skip("no US to attribute the commit to")
    ids = {s.get("id") for s in _load_board(dash).get("stories", [])}
    if ids and us not in ids:
        return _skip(f"US {us} not on the board")
    # set active (records the commit boundary in the uslog) then reconcile the delta onto it
    cur = _read_active()
    cur.update({"session_id": session, "us_id": us,
                "at": datetime.now().astimezone().isoformat()})
    _write_active(cur)
    _append_uslog(session, us)
    res = _cli(dash, "reconcile", "--session", session, "--current-us", us,
               "--uslog", _uslog_path(session), "--watermark", _watermark_path(session))
    print(json.dumps({"tracking": "commit-attributed", "session_id": session,
                      "us_id": us, "result": res or "skipped (CLI unavailable)"}))
    return 0


def cmd_focus(a) -> int:
    """Snapshot the CURRENT development subject to a focus file, so a compaction can be steered
    back onto it. PreCompact can't edit the summary, but SessionStart(source=compact) re-injects
    this — giving a working summary FOR THE DEV IN PROGRESS, not a generic global recap. Captures
    the active US (title/acceptance/goal, its feature+epic) + live git context (branch, recent
    commits, changed files) + any manual `/compact` instructions. Fail-open; writes best-effort."""
    session = a.session or _read_active().get("session_id", "")
    active = _read_active()
    us_id = (active.get("us_id", "") if active.get("session_id") == session else "") or active.get("us_id", "")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or _branch()

    title = accept = so_that = feat_title = epic_title = ""
    dash = _dash_dir()
    if dash and us_id:
        board = _load_board(dash)
        st = next((s for s in board.get("stories", []) if s.get("id") == us_id), None)
        if st:
            title = st.get("title", "")
            ac = st.get("acceptance_criteria") or []
            accept = "; ".join(ac) if isinstance(ac, list) else str(ac)
            so_that = st.get("so_that", "")
            fe = next((f for f in board.get("features", []) if f.get("id") == st.get("feature_id")), None)
            if fe:
                feat_title = fe.get("title", "")
                ep = next((e for e in board.get("epics", []) if e.get("id") == fe.get("epic_id")), None)
                epic_title = ep.get("title", "") if ep else ""

    commits = _git("log", "-3", "--pretty=- %s")
    changed = _git("status", "--porcelain")
    # strip the 1-2 char XY status + spaces (robust even if the leading line got whitespace-trimmed)
    files = [re.sub(r"^[ MADRCU?!]{1,2}\s+", "", ln) for ln in changed.splitlines() if ln.strip()][:12]
    trigger = getattr(a, "trigger", "") or "manual"
    instr = (getattr(a, "instructions", "") or "").strip()

    subject = f"`{us_id}` — {title}" if us_id and title else (f"`{us_id}`" if us_id else f"branch `{branch}`")
    L: list[str] = []
    L.append("# Active development subject (compaction focus)")
    L.append("")
    L.append(f"> Snapshot taken before a **{trigger}** compaction. After compaction, continue THIS — "
             "it is the work in progress, not a global recap. Treat unrelated history as compressible.")
    L.append("")
    L.append(f"**Working on:** {subject}")
    if feat_title or epic_title:
        L.append(f"**Feature / Epic:** {feat_title or '?'} / {epic_title or '?'}")
    L.append(f"**Branch:** `{branch}`")
    if so_that:
        L.append(f"**Goal:** {so_that}")
    if accept:
        L.append(f"**Acceptance:** {accept}")
    L.append("")
    if commits:
        L.append("**Recent commits:**")
        L.append(commits)
        L.append("")
    if files:
        L.append("**Uncommitted / in-flight files:**")
        L.extend(f"- `{f}`" for f in files)
        L.append("")
    L.append("**Preserve in the summary:** the goal + acceptance of the active US, decisions made, "
             "files touched, what is DONE vs REMAINING, blockers, and the immediate next step.")
    if instr:
        L.append("")
        L.append(f"**Manual /compact instructions:** {instr}")
    L.append("")

    try:
        with open(_focus_path(), "w") as f:
            f.write("\n".join(L))
    except Exception as e:
        return _skip(f"focus write failed: {e}")
    print(json.dumps({"tracking": "focus", "us_id": us_id or None,
                      "subject": subject, "path": _focus_path(), "trigger": trigger}))
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

    a = sub.add_parser("attribute-commit"); a.add_argument("--session", default="")
    a.add_argument("--id", default=""); a.add_argument("--summary", default="")
    a.add_argument("--branch", default=""); a.set_defaults(fn=cmd_attribute_commit)

    a = sub.add_parser("focus"); a.add_argument("--session", default="")
    a.add_argument("--trigger", default=""); a.add_argument("--instructions", default="")
    a.set_defaults(fn=cmd_focus)

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
