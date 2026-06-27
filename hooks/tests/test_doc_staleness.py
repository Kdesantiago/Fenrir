"""Tests for the Fenrir Stop hook hooks/doc-staleness.py.

The hook is a Claude Code *Stop* hook. It reads a JSON event from stdin and:
  - emits {"decision":"block","reason":...} on stdout + exit 0 when code files
    changed this session (per `git diff` / `git diff --cached`) but CHANGELOG.md
    was NOT touched (the single deny/block path);
  - otherwise exits 0 with no stdout (allow / no-op).
It is loop-safe (no-op when stop_hook_active is truthy) and fails OPEN on any
trouble (bad stdin, non-git dir, git failure) -> exit 0, no block.

These tests drive the REAL hook via subprocess with crafted stdin, and isolate
all side effects inside a pytest tmp_path git repo (CLAUDE_PROJECT_DIR + cwd).
stdlib + pytest only. Self-contained: no conftest/__init__.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "doc-staleness.py"

BLOCK_REASON_SNIPPET = "CHANGELOG.md was not updated"


def run_hook(payload, project_dir):
    """Invoke the hook with `payload` (dict | raw str | None) piped to stdin.

    Returns (returncode, stdout_str). CLAUDE_PROJECT_DIR + cwd point at
    `project_dir` so all git inspection and any side effects stay sandboxed.
    """
    if payload is None:
        stdin = ""
    elif isinstance(payload, str):
        stdin = payload
    else:
        stdin = json.dumps(payload)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env={"CLAUDE_PROJECT_DIR": str(project_dir), "PATH": _path_env()},
        timeout=30,
    )
    return proc.returncode, proc.stdout


def _path_env():
    import os

    return os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin")


def git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A fresh git repo with a committed code file and CHANGELOG, returned as Path."""
    r = tmp_path / "proj"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "test@example.com")
    git(r, "config", "user.name", "test")
    (r / "app.py").write_text("print('hi')\n")
    (r / "CHANGELOG.md").write_text("# Changelog\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


# --- deny / block path -------------------------------------------------------


def test_block_when_code_changed_no_changelog(repo):
    (repo / "app.py").write_text("print('changed')\n")
    code, out = run_hook({"hook_event_name": "Stop"}, repo)
    assert code == 0
    payload = json.loads(out)
    assert payload["decision"] == "block"
    assert BLOCK_REASON_SNIPPET in payload["reason"]


def test_block_on_staged_code_change(repo):
    """Staged-only code change is detected via `git diff --cached` -> block."""
    (repo / "app.py").write_text("print('staged')\n")
    git(repo, "add", "app.py")
    code, out = run_hook({"hook_event_name": "Stop"}, repo)
    assert code == 0
    assert json.loads(out)["decision"] == "block"


def test_block_on_new_src_dir_file_without_changelog(repo):
    """A non-code extension under src/ still counts as code (startswith 'src/')."""
    (repo / "src").mkdir()
    (repo / "src" / "config.yaml").write_text("a: 1\n")
    git(repo, "add", "src/config.yaml")
    code, out = run_hook({"hook_event_name": "Stop"}, repo)
    assert code == 0
    assert json.loads(out)["decision"] == "block"


# --- allow / no-op paths -----------------------------------------------------


def test_allow_when_changelog_also_touched(repo):
    (repo / "app.py").write_text("print('changed')\n")
    (repo / "CHANGELOG.md").write_text("# Changelog\n- entry\n")
    code, out = run_hook({"hook_event_name": "Stop"}, repo)
    assert code == 0
    assert out.strip() == ""


def test_allow_when_no_changes(repo):
    code, out = run_hook({"hook_event_name": "Stop"}, repo)
    assert code == 0
    assert out.strip() == ""


def test_allow_when_only_test_files_changed(repo):
    """Test-ish paths are excluded from 'code_changed' -> no block."""
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text("def test_x():\n    assert True\n")
    git(repo, "add", "tests/test_app.py")
    code, out = run_hook({"hook_event_name": "Stop"}, repo)
    assert code == 0
    assert out.strip() == ""


def test_allow_when_only_non_code_changed(repo):
    """A plain doc file (not code, not under src/) does not trigger a block."""
    (repo / "README.md").write_text("# readme\nedited\n")
    git(repo, "add", "README.md")
    code, out = run_hook({"hook_event_name": "Stop"}, repo)
    assert code == 0
    assert out.strip() == ""


# --- loop-safety -------------------------------------------------------------


@pytest.mark.parametrize("active", [True, 1, "yes"])
def test_noop_when_stop_hook_active(repo, active):
    """Even with a blockable diff present, a truthy stop_hook_active = no-op."""
    (repo / "app.py").write_text("print('changed')\n")
    code, out = run_hook(
        {"hook_event_name": "Stop", "stop_hook_active": active}, repo
    )
    assert code == 0
    assert out.strip() == ""


# --- fail-open paths ---------------------------------------------------------


@pytest.mark.parametrize("bad", ["not json", "", "   ", "{ broken", "[1,2,3"])
def test_fail_open_on_bad_stdin(repo, bad):
    """Malformed/empty stdin -> graceful no-op, exit 0, no block (fail-open)."""
    code, out = run_hook(bad, repo)
    assert code == 0
    assert out.strip() == ""


def test_fail_open_in_non_git_dir(tmp_path):
    """No git repo -> hook cannot determine changes -> exit 0, no block."""
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "app.py").write_text("print('hi')\n")
    code, out = run_hook({"hook_event_name": "Stop"}, plain)
    assert code == 0
    assert out.strip() == ""
