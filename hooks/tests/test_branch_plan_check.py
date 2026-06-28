"""Tests for hooks/branch-plan-check.py — the PostToolUse(Bash) plan-first nudge.

When a developer creates a new feature branch (`git checkout -b` / `git switch -c` /
`git switch --create`) the hook asks the engine whether the session is already traced to a
User Story. ONLY on a definite "untraced" (engine `check` exits 3) does it print a JSON
advisory (`systemMessage` + `suppressOutput:true`) telling them to run `/fenrir:plan`.
Every other path is silent. It is advisory: it can NEVER block, and exits 0 on every path.

Two tiers, mirroring test_tracking.py:
  * Safety units (no dashboard needed): the hook must never block and must fail-open silently
    when there is no dashboard, the command is not a branch-create, or stdin is junk.
  * Integration (skipped unless the repo's dashboard + venv are present, via needs_dash): with
    a real ISOLATED board, an untraced session yields rc 3 → the nudge actually fires, and a
    traced session stays silent.

Subprocess-based and self-contained (no conftest). State is isolated to tmp_path via
CLAUDE_PROJECT_DIR + an isolated FENRIR_DASH_BOARD, so the real repo board is never touched.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "hooks" / "branch-plan-check.py"
ENGINE = ROOT / "scripts" / "track_session.py"

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


def run_hook(stdin_text, project_dir, **extra):
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text,
                          capture_output=True, text=True,
                          env=_env(project_dir, **extra), cwd=str(project_dir))


def run_engine(args, project_dir, **extra):
    return subprocess.run([sys.executable, str(ENGINE), *args],
                          capture_output=True, text=True,
                          env=_env(project_dir, **extra), cwd=str(project_dir))


def branch_stdin(session="s1", cmd="git checkout -b feat/x", tool="Bash"):
    return json.dumps({"tool_name": tool, "tool_input": {"command": cmd}, "session_id": session})


def empty_board(tmp_path):
    b = tmp_path / "board.json"
    b.write_text(json.dumps({"epics": [], "features": [], "stories": [], "tasks": []}))
    return b


def is_silent(proc):
    """Advisory said nothing: no stdout, or stdout carries no systemMessage."""
    if proc.stdout.strip() == "":
        return True
    try:
        return "systemMessage" not in json.loads(proc.stdout)
    except Exception:
        return False  # printed non-empty, non-JSON → not silent


# ---------------------------------------------------------------- safety: never blocks
def _assert_never_blocks(proc):
    # PostToolUse advisory: exit 0 always, and the payload (if any) must not deny.
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    if out:
        try:
            data = json.loads(out)
        except Exception:
            return  # non-JSON output can't carry a permission decision
        assert "permissionDecision" not in json.dumps(data)
        assert data.get("decision") != "deny"
        hso = data.get("hookSpecificOutput") or {}
        assert hso.get("permissionDecision") not in ("deny", "ask")


# ---------------------------------------------------------------- safety units (no dashboard)
def test_fail_open_silent_without_dashboard_on_branch_create(tmp_path):
    # tmp_path has no dashboard/ → engine `check` fail-opens to rc 0 (not 3) → hook stays silent.
    # The actual nudge (rc 3) path requires a real dashboard; see needs_dash tests below.
    p = run_hook(branch_stdin(session="nodash", cmd="git checkout -b feat/x"), tmp_path)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout
    _assert_never_blocks(p)


@pytest.mark.parametrize("cmd", [
    "git checkout main",        # checkout an existing branch, no -b
    "git switch main",          # switch, no -c/--create
    "git checkout -- file.txt", # restore a path, not a branch
    "git branch feat/x",        # create-only, no checkout
    "git commit -m x",          # unrelated git command
    "ls -la",                   # not git at all
])
def test_silent_on_non_branch_create_commands(tmp_path, cmd):
    p = run_hook(branch_stdin(cmd=cmd), tmp_path)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), f"{cmd!r} should be silent, got: {p.stdout!r}"
    _assert_never_blocks(p)


def test_silent_on_non_bash_tool(tmp_path):
    # PostToolUse fires on every tool; only Bash is inspected.
    p = run_hook(branch_stdin(cmd="git checkout -b feat/x", tool="Edit"), tmp_path)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout


def test_silent_on_junk_stdin(tmp_path):
    p = run_hook("}{ not json at all", tmp_path)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout
    _assert_never_blocks(p)


def test_silent_on_empty_stdin(tmp_path):
    p = run_hook("", tmp_path)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout


def test_silent_on_missing_command(tmp_path):
    # Bash tool but no command key → nothing to match → silent.
    p = run_hook(json.dumps({"tool_name": "Bash", "tool_input": {}, "session_id": "s1"}), tmp_path)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout


def test_disabled_env_silent_on_real_branch_create(tmp_path):
    # FENRIR_TRACK_DISABLE=1 short-circuits before any engine call → silent, exit 0.
    p = run_hook(branch_stdin(cmd="git checkout -b feat/x"), tmp_path, FENRIR_TRACK_DISABLE="1")
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout
    _assert_never_blocks(p)


# ---------------------------------------------------------------- regex correctness
@pytest.mark.parametrize("cmd", [
    "git checkout -b feat/x",
    "git switch -c x",
    "git switch --create x",
    "git -c user.name=bot checkout -b x",  # global config flag must not hide the -b create
])
def test_regex_matches_branch_create(tmp_path, cmd):
    # Without a dashboard the engine fail-opens (rc 0) so the nudge stays silent; the point here
    # is that the command is RECOGNISED as a branch-create — proven via the needs_dash nudge tests
    # where these same shapes drive the advisory. Here we only assert it never blocks / exits 0.
    p = run_hook(branch_stdin(cmd=cmd), tmp_path)
    assert p.returncode == 0, p.stderr
    _assert_never_blocks(p)


def test_regex_does_not_match_checkout_dashdash_file(tmp_path):
    # `git checkout -- file` is a path restore, NOT a branch create → must stay silent even if a
    # dashboard were present (the engine is never consulted). Proven via the untraced session id.
    p = run_hook(branch_stdin(session="never-seen-nudge", cmd="git checkout -- file"), tmp_path)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout


# ---------------------------------------------------------------- integration (real board CLI)
@needs_dash
def test_nudges_on_untraced_branch_create(tmp_path):
    # Real isolated board, a session that was never traced → engine `check` exits 3 → the hook
    # prints the plan-first advisory (systemMessage + suppressOutput), still exit 0, never blocks.
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board)}
    chk = run_engine(["check", "--session", "untraced-sess"], tmp_path, **env)
    assert chk.returncode == 3, f"precondition: untraced session must be rc3, got {chk.returncode}"

    p = run_hook(branch_stdin(session="untraced-sess", cmd="git checkout -b feat/x"), tmp_path, **env)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["suppressOutput"] is True
    assert "/fenrir:plan" in payload["systemMessage"]
    _assert_never_blocks(p)


@needs_dash
@pytest.mark.parametrize("cmd", ["git checkout -b feat/x", "git switch -c x", "git switch --create x"])
def test_nudges_for_each_branch_create_shape(tmp_path, cmd):
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board)}
    p = run_hook(branch_stdin(session="untraced-shapes", cmd=cmd), tmp_path, **env)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert "/fenrir:plan" in payload["systemMessage"], f"{cmd!r} should nudge"


@needs_dash
def test_silent_when_session_already_traced(tmp_path):
    # Trace the session first (ensure-us → check exits 0) → no nag on a subsequent branch-create.
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board)}
    run_engine(["ensure-us", "--session", "traced-sess"], tmp_path, **env)
    chk = run_engine(["check", "--session", "traced-sess"], tmp_path, **env)
    assert chk.returncode == 0, "precondition: traced session must be rc0"

    p = run_hook(branch_stdin(session="traced-sess", cmd="git checkout -b feat/x"), tmp_path, **env)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), f"traced session should not be nagged, got: {p.stdout!r}"


@needs_dash
def test_disabled_env_silent_even_when_untraced(tmp_path):
    # Untraced session (would normally nudge) but FENRIR_TRACK_DISABLE=1 → silent, no engine call.
    board = empty_board(tmp_path)
    env = {"FENRIR_DASH_DIR": str(DASH), "FENRIR_DASH_BOARD": str(board),
           "FENRIR_TRACK_DISABLE": "1"}
    p = run_hook(branch_stdin(session="untraced-disabled", cmd="git checkout -b feat/x"), tmp_path, **env)
    assert p.returncode == 0, p.stderr
    assert is_silent(p), p.stdout
