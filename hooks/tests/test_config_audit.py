"""Tests for the Fenrir config-audit PostToolUse hook.

The hook (hooks/config-audit.py) is a non-blocking PostToolUse hook on
Write/Edit/MultiEdit. When a `settings.json` / `settings.local.json` file is
touched, it diffs the file's current content against a stored snapshot and
appends a line to `.claude/audit/config-changes.jsonl`, flagging changes to
sensitive keys. It NEVER blocks: it always exits 0 and prints nothing to stdout.

These tests are subprocess-based and self-contained (no conftest / no __init__).
Side effects are isolated to pytest's tmp_path via CLAUDE_PROJECT_DIR + cwd.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "config-audit.py"


def run_hook(stdin_text, project_dir):
    """Invoke the hook with stdin_text piped in. Returns CompletedProcess.

    project_dir is exported as CLAUDE_PROJECT_DIR and used as cwd so that all
    audit files land under the test's tmp_path, never the real repo.
    """
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env={"CLAUDE_PROJECT_DIR": str(project_dir), "PATH": "/usr/bin:/bin"},
        cwd=str(project_dir),
    )


def write_settings(project_dir, content):
    """Write a settings.json under <project_dir>/.claude/ and return its path."""
    claude = project_dir / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    settings = claude / "settings.json"
    settings.write_text(json.dumps(content))
    return settings


def audit_dir(project_dir):
    return project_dir / ".claude" / "audit"


def jsonl_path(project_dir):
    return audit_dir(project_dir) / "config-changes.jsonl"


def read_jsonl(project_dir):
    """Return parsed audit lines, or [] if the file does not exist."""
    p = jsonl_path(project_dir)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def make_event(file_path, tool_name="Write", session_id="sess-1"):
    return json.dumps(
        {
            "tool_name": tool_name,
            "tool_input": {"file_path": str(file_path)},
            "session_id": session_id,
        }
    )


# --------------------------------------------------------------------------
# Core path: a real settings change is audited.
# --------------------------------------------------------------------------


def test_settings_change_appends_audit_line_and_snapshot(tmp_path):
    settings = write_settings(tmp_path, {"permissions": {"allow": ["Bash"]}})
    res = run_hook(make_event(settings, session_id="abc"), tmp_path)

    assert res.returncode == 0
    assert res.stdout == ""  # non-blocking: never emits a permission decision

    lines = read_jsonl(tmp_path)
    assert len(lines) == 1
    rec = lines[0]
    assert rec["file"] == str(settings)
    assert rec["session"] == "abc"
    assert rec["changed_keys"] == ["permissions"]
    assert rec["sensitive"] == ["permissions"]
    assert "ts" in rec

    # snapshot is written so subsequent identical runs are no-ops
    snap = audit_dir(tmp_path) / ".settings.snapshot.json"
    assert snap.exists()
    assert json.loads(snap.read_text()) == {"permissions": {"allow": ["Bash"]}}


@pytest.mark.parametrize("tool_name", ["Write", "Edit", "MultiEdit"])
def test_all_mutating_tools_are_audited(tmp_path, tool_name):
    settings = write_settings(tmp_path, {"env": {"X": "1"}})
    res = run_hook(make_event(settings, tool_name=tool_name), tmp_path)

    assert res.returncode == 0
    lines = read_jsonl(tmp_path)
    assert len(lines) == 1
    assert lines[0]["sensitive"] == ["env"]


@pytest.mark.parametrize(
    "key,sensitive_expected",
    [
        ("permissions", True),
        ("hooks", True),
        ("env", True),
        ("mcpServers", True),
        ("allowedHttpHookUrls", True),
        ("model", False),  # non-sensitive key: audited but not flagged
        ("theme", False),
    ],
)
def test_sensitive_key_flagging(tmp_path, key, sensitive_expected):
    settings = write_settings(tmp_path, {key: {"a": 1}})
    res = run_hook(make_event(settings), tmp_path)

    assert res.returncode == 0
    lines = read_jsonl(tmp_path)
    assert len(lines) == 1
    assert lines[0]["changed_keys"] == [key]
    if sensitive_expected:
        assert lines[0]["sensitive"] == [key]
    else:
        assert lines[0]["sensitive"] == []


def test_settings_local_json_is_also_audited(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    local = claude / "settings.local.json"
    local.write_text(json.dumps({"hooks": {"PreToolUse": []}}))

    res = run_hook(make_event(local), tmp_path)
    assert res.returncode == 0
    lines = read_jsonl(tmp_path)
    assert len(lines) == 1
    assert lines[0]["file"] == str(local)
    assert lines[0]["sensitive"] == ["hooks"]


# --------------------------------------------------------------------------
# No-op / allow paths: hook exits 0 and writes no audit line.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", ["Read", "Bash", "Glob", "Grep", ""])
def test_non_mutating_tool_is_noop(tmp_path, tool_name):
    settings = write_settings(tmp_path, {"permissions": {"allow": ["Bash"]}})
    res = run_hook(make_event(settings, tool_name=tool_name), tmp_path)

    assert res.returncode == 0
    assert res.stdout == ""
    assert read_jsonl(tmp_path) == []
    # bailed before makedirs: audit dir not even created
    assert not audit_dir(tmp_path).exists()


@pytest.mark.parametrize(
    "fp",
    [
        "/some/dir/foo.txt",
        "/some/dir/config.json",
        "/some/dir/settings.json.bak",
        "/some/dir/mysettings.json",  # no path-separator/start boundary before "settings"
        "/some/dir/settings.prod.json",
    ],
)
def test_non_settings_path_is_noop(tmp_path, fp):
    res = run_hook(make_event(fp), tmp_path)
    assert res.returncode == 0
    assert res.stdout == ""
    assert read_jsonl(tmp_path) == []
    assert not audit_dir(tmp_path).exists()


def test_no_change_does_not_append_second_line(tmp_path):
    settings = write_settings(tmp_path, {"permissions": {"allow": ["Bash"]}})
    first = run_hook(make_event(settings), tmp_path)
    assert first.returncode == 0
    assert len(read_jsonl(tmp_path)) == 1

    # Re-run with identical file content: snapshot == current, no diff.
    second = run_hook(make_event(settings, session_id="sess-2"), tmp_path)
    assert second.returncode == 0
    assert len(read_jsonl(tmp_path)) == 1  # still just the one line


def test_settings_path_matches_but_file_absent_writes_nothing(tmp_path):
    # Path matches the settings regex, but no file exists on disk -> cur == {}
    # and prev == {}, so changed is empty: dir is created but no jsonl written.
    missing = tmp_path / ".claude" / "settings.json"
    res = run_hook(make_event(missing), tmp_path)

    assert res.returncode == 0
    assert res.stdout == ""
    # makedirs ran (tool + path checks passed) but no audit line was appended.
    assert audit_dir(tmp_path).exists()
    assert not jsonl_path(tmp_path).exists()


# --------------------------------------------------------------------------
# Malformed / empty stdin.
#
# Unparseable input (empty, whitespace, invalid syntax) is caught by the
# try/except around json.load and exits 0 -- a graceful no-op, which is the
# fail-safe behavior expected of a non-blocking PostToolUse hook.
#
# HOOK BUG (asserted as current behavior, not endorsed): JSON that parses but
# is NOT an object (null / int / list / string) slips past the json.load
# except-guard, then `data.get(...)` raises AttributeError -> the hook crashes
# with exit code 1. Harmless in practice (PostToolUse ignores non-zero exits)
# but it is an unhandled-exception code path. See notes.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stdin_text", ["", "   ", "not json{", "{ bad json"])
def test_unparseable_stdin_is_graceful_noop(tmp_path, stdin_text):
    res = run_hook(stdin_text, tmp_path)
    assert res.returncode == 0
    assert res.stdout == ""
    assert read_jsonl(tmp_path) == []


@pytest.mark.parametrize("stdin_text", ["null", "42", "[1,2,3]", '"hi"'])
def test_non_object_json_is_graceful_noop(tmp_path, stdin_text):
    # valid-but-non-object JSON (null/scalar/list) -> graceful no-op exit 0,
    # guarded by `isinstance(data, dict)` (was an uncaught AttributeError -> exit 1).
    res = run_hook(stdin_text, tmp_path)
    assert res.returncode == 0
    assert res.stdout == ""  # no permission decision
    assert read_jsonl(tmp_path) == []


def test_missing_tool_input_is_noop(tmp_path):
    # tool_name present and mutating, but no tool_input -> file_path "" -> no match
    res = run_hook(json.dumps({"tool_name": "Write"}), tmp_path)
    assert res.returncode == 0
    assert res.stdout == ""
    assert read_jsonl(tmp_path) == []


def test_null_tool_input_is_noop(tmp_path):
    # tool_input explicitly null -> the `or {}` guard kicks in, file_path "".
    res = run_hook(
        json.dumps({"tool_name": "Edit", "tool_input": None}), tmp_path
    )
    assert res.returncode == 0
    assert res.stdout == ""
    assert read_jsonl(tmp_path) == []
