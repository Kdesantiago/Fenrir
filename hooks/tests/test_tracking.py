"""Tests for the Fenrir delivery-tracking infra.

Covers the deterministic engine (scripts/track_session.py) and the three hooks:
  - tracking-guard.py    (PreToolUse Bash — make tracing a git commit obligatory)
  - tracking-collect.py  (SubagentStop — ledger a subagent run)
  - tracking-finalize.py (SessionEnd — auto-attribute the session cost)

Two tiers:
  * Safety units (no dashboard needed): the hooks must NEVER brick a session — they fail-open
    when there is no dashboard, when stdin is junk, or when the command is not a commit.
  * Integration (skipped unless the repo's dashboard + its venv are present): the engine really
    creates a User Story on an ISOLATED tmp board (FENRIR_DASH_BOARD) and the guard enforces it.

Subprocess-based and self-contained (no conftest). All side effects are isolated to tmp_path
via CLAUDE_PROJECT_DIR (tracking state) + FENRIR_DASH_BOARD (a throwaway board file), so the
real repo board is never touched.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "scripts" / "track_session.py"
GUARD = ROOT / "hooks" / "tracking-guard.py"
COLLECT = ROOT / "hooks" / "tracking-collect.py"
FINALIZE = ROOT / "hooks" / "tracking-finalize.py"

DASH = ROOT / "dashboard"
DASH_PY = DASH / ".venv" / "bin" / "python"
HAS_DASH = (DASH / "backend").is_dir() and DASH_PY.exists()
needs_dash = pytest.mark.skipif(not HAS_DASH, reason="dashboard companion app + venv not present")


def _env(project_dir, **extra):
    e = {"CLAUDE_PROJECT_DIR": str(project_dir), "PATH": "/usr/bin:/bin"}
    home = Path.home()
    if home:
        e["HOME"] = str(home)  # the dashboard venv python may want HOME
    e.update({k: v for k, v in extra.items() if v is not None})
    return e


def run_engine(args, project_dir, **extra):
    return subprocess.run([sys.executable, str(ENGINE), *args],
                          capture_output=True, text=True,
                          env=_env(project_dir, **extra), cwd=str(project_dir))


def run_hook(hook, stdin_text, project_dir, **extra):
    return subprocess.run([sys.executable, str(hook)], input=stdin_text,
                          capture_output=True, text=True,
                          env=_env(project_dir, **extra), cwd=str(project_dir))


def commit_stdin(session="s1", cmd="git commit -m work"):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": session})


def decision(proc):
    return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]


def empty_board(tmp_path):
    b = tmp_path / "board.json"
    b.write_text(json.dumps({"epics": [], "features": [], "stories": [], "tasks": []}))
    return b


# ---------------------------------------------------------------- safety units (no dashboard)
def test_guard_allows_non_commit(tmp_path):
    p = run_hook(GUARD, commit_stdin(cmd="ls -la"), tmp_path)
    assert p.returncode == 0
    assert decision(p) == "allow"


def test_guard_allows_amend(tmp_path):
    p = run_hook(GUARD, commit_stdin(cmd="git commit --amend --no-edit"), tmp_path)
    assert decision(p) == "allow"


def test_guard_allows_on_junk_stdin(tmp_path):
    p = run_hook(GUARD, "not json at all", tmp_path)
    assert p.returncode == 0
    assert decision(p) == "allow"


def test_guard_fail_open_without_dashboard(tmp_path):
    # tmp_path has no dashboard/ → engine check fail-opens → guard allows the commit.
    p = run_hook(GUARD, commit_stdin(session="nodash"), tmp_path)
    assert decision(p) == "allow"


def test_guard_strict_still_fail_open_without_dashboard(tmp_path):
    # strict must NOT block when tracking is impossible (no board) — never brick.
    p = run_hook(GUARD, commit_stdin(session="nodash"), tmp_path, FENRIR_TRACK_ENFORCE="strict")
    assert decision(p) == "allow"


def test_guard_disabled_env(tmp_path):
    p = run_hook(GUARD, commit_stdin(session="x"), tmp_path,
                 FENRIR_TRACK_DISABLE="1", FENRIR_TRACK_ENFORCE="strict")
    assert decision(p) == "allow"


def test_engine_skips_without_dashboard(tmp_path):
    p = run_engine(["ensure-us", "--session", "s1"], tmp_path)
    assert p.returncode == 0
    assert json.loads(p.stdout)["tracking"] == "skipped"


def test_engine_check_fail_open_without_dashboard(tmp_path):
    p = run_engine(["check", "--session", "s1"], tmp_path)
    assert p.returncode == 0  # untracked-ok, not a block


def test_set_us_sets_active_without_dashboard(tmp_path):
    # no board to validate against → still records the active US (write active.json), exit 0
    p = run_engine(["set-us", "--id", "us-7", "--session", "sZ"], tmp_path)
    assert p.returncode == 0
    active = tmp_path / ".claude" / "tracking" / "active.json"
    assert active.exists()
    assert json.loads(active.read_text())["us_id"] == "us-7"


@needs_dash
def test_set_us_rejects_unknown_us(tmp_path):
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board)}
    run_engine(["ensure-us", "--session", "sZ"], tmp_path, **env)  # seed a real US
    p = run_engine(["set-us", "--id", "us-999", "--session", "sZ"], tmp_path, **env)
    assert p.returncode == 0
    assert json.loads(p.stdout)["tracking"] == "skipped"  # us-999 not on the board


def test_collect_run_writes_ledger(tmp_path):
    p = run_engine(["collect-run", "--session", "sX", "--run", "agent-1", "--type", "reviewer"], tmp_path)
    assert p.returncode == 0
    ledger = tmp_path / ".claude" / "tracking" / "sX.runs.jsonl"
    assert ledger.exists()
    row = json.loads(ledger.read_text().strip())
    assert row["run"] == "agent-1" and row["type"] == "reviewer"


def test_collect_hook_derives_run_from_transcript(tmp_path):
    stdin = json.dumps({"session_id": "sT", "transcript_path": "/a/b/agent-deadbeef.jsonl",
                        "subagent_type": "fenrir:architect"})
    p = run_hook(COLLECT, stdin, tmp_path)
    assert p.returncode == 0
    ledger = tmp_path / ".claude" / "tracking" / "sT.runs.jsonl"
    assert ledger.exists()
    assert json.loads(ledger.read_text().strip())["run"] == "agent-deadbeef"


def test_collect_hook_noop_without_ids(tmp_path):
    p = run_hook(COLLECT, json.dumps({"foo": "bar"}), tmp_path)
    assert p.returncode == 0
    assert not (tmp_path / ".claude" / "tracking").exists()


def test_finalize_hook_disabled_env(tmp_path):
    p = run_hook(FINALIZE, json.dumps({"session_id": "s1"}), tmp_path, FENRIR_TRACK_DISABLE="1")
    assert p.returncode == 0


def test_finalize_hook_survives_junk(tmp_path):
    p = run_hook(FINALIZE, "}{ not json", tmp_path)
    assert p.returncode == 0


# ---------------------------------------------------------------- integration (real board CLI)
@needs_dash
def test_ensure_us_creates_and_is_idempotent(tmp_path):
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board)}
    a = run_engine(["ensure-us", "--session", "sess-1", "--summary", "unit"], tmp_path, **env)
    assert a.returncode == 0, a.stderr
    us = json.loads(a.stdout)["us_id"]
    b = run_engine(["ensure-us", "--session", "sess-1"], tmp_path, **env)
    assert json.loads(b.stdout)["us_id"] == us  # same US, no duplicate
    data = json.loads(board.read_text())
    assert len(data["stories"]) == 1
    assert data["epics"][0]["title"] == "Auto-tracked sessions"


@needs_dash
def test_check_traced_after_ensure(tmp_path):
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board)}
    run_engine(["ensure-us", "--session", "sess-2"], tmp_path, **env)
    chk = run_engine(["check", "--session", "sess-2"], tmp_path, **env)
    assert chk.returncode == 0
    other = run_engine(["check", "--session", "never-seen"], tmp_path, **env)
    assert other.returncode == 3  # untraced → non-zero


@needs_dash
def test_guard_auto_creates_on_commit(tmp_path):
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board)}
    p = run_hook(GUARD, commit_stdin(session="sess-auto"), tmp_path, **env)
    assert decision(p) == "allow"
    assert len(json.loads(board.read_text())["stories"]) == 1


@needs_dash
def test_guard_strict_denies_untraced_then_allows_traced(tmp_path):
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board),
           "FENRIR_TRACK_ENFORCE": "strict"}
    denied = run_hook(GUARD, commit_stdin(session="sess-strict"), tmp_path, **env)
    assert decision(denied) == "deny"
    assert json.loads(board.read_text())["stories"] == []  # strict does NOT auto-create
    # now trace it explicitly, then the same session's commit is allowed
    run_engine(["ensure-us", "--session", "sess-strict"], tmp_path,
               FENRIR_DASH_DIR=str(DASH), FENRIR_DASH_BOARD=str(board))
    allowed = run_hook(GUARD, commit_stdin(session="sess-strict"), tmp_path, **env)
    assert decision(allowed) == "allow"
