"""Tests for the Fenrir PostToolUseFailure hook: tool-failure-triage.py.

This hook is NON-BLOCKING: it always exits 0. Its observable behavior is:
  - a triage hint written to STDERR (not stdout) for known tools (Bash/Edit/Write),
  - an appended JSONL record under <root>/.claude/audit/tool-failures.jsonl,
  - on empty/malformed stdin it no-ops (exit 0, no audit file, no hint).

Stdout is ALWAYS empty. The audit root is CLAUDE_PROJECT_DIR (falling back to cwd).
All tests are subprocess-based and isolate side effects via tmp_path.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "tool-failure-triage.py"

# Hints live in the hook's HINTS dict; we assert on a stable substring of each.
HINT_SUBSTR = {
    "Bash": "check the command's exit output",
    "Edit": "old_string likely didn't match",
    "Write": "path or permissions issue",
}


def run_hook(payload, project_dir):
    """Invoke the hook with `payload` piped to stdin.

    `payload` may be a dict (json-encoded) or a raw str (sent verbatim, for the
    malformed/empty cases). Returns the CompletedProcess.
    """
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env={"CLAUDE_PROJECT_DIR": str(project_dir)},
        cwd=str(project_dir),
    )


def read_audit(project_dir):
    """Return the parsed JSONL records from the audit file (empty list if absent)."""
    f = Path(project_dir) / ".claude" / "audit" / "tool-failures.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("tool", ["Bash", "Edit", "Write"])
def test_known_tool_emits_hint_on_stderr_and_audits(tool, tmp_path):
    """Known tools: exit 0, hint on STDERR, empty stdout, one audit record."""
    proc = run_hook({"tool_name": tool, "tool_error": "boom"}, tmp_path)
    assert proc.returncode == 0
    assert proc.stdout == ""  # stdout is always empty for this hook
    assert HINT_SUBSTR[tool] in proc.stderr
    assert tool in proc.stderr

    records = read_audit(tmp_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["tool"] == tool
    assert rec["error"] == "boom"
    assert "ts" in rec


def test_error_field_alias_accepted(tmp_path):
    """The hook accepts `error` as an alias for `tool_error`."""
    proc = run_hook({"tool_name": "Edit", "error": "no match"}, tmp_path)
    assert proc.returncode == 0
    assert HINT_SUBSTR["Edit"] in proc.stderr
    assert read_audit(tmp_path)[0]["error"] == "no match"


def test_unknown_tool_no_hint_but_still_audits(tmp_path):
    """Unknown tool: no hint emitted, but failure is still recorded. Exit 0."""
    proc = run_hook({"tool_name": "Grep", "tool_error": "x"}, tmp_path)
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert "fenrir triage" not in proc.stderr  # no hint for unknown tools
    records = read_audit(tmp_path)
    assert len(records) == 1
    assert records[0]["tool"] == "Grep"


def test_missing_tool_name_no_hint_audits_empty_tool(tmp_path):
    """Missing tool_name -> tool defaults to "", no hint, still audited."""
    proc = run_hook({"tool_error": "orphan failure"}, tmp_path)
    assert proc.returncode == 0
    assert "fenrir triage" not in proc.stderr
    records = read_audit(tmp_path)
    assert len(records) == 1
    assert records[0]["tool"] == ""
    assert records[0]["error"] == "orphan failure"


def test_non_string_tool_name_coerced_to_empty(tmp_path):
    """A non-string tool_name is coerced to "" (no hint), audited as ""."""
    proc = run_hook({"tool_name": 123, "tool_error": "y"}, tmp_path)
    assert proc.returncode == 0
    assert "fenrir triage" not in proc.stderr
    assert read_audit(tmp_path)[0]["tool"] == ""


def test_non_string_error_is_json_serialized(tmp_path):
    """A non-string error object is json.dumps'd into the audit record."""
    proc = run_hook({"tool_name": "Bash", "tool_error": {"code": 1}}, tmp_path)
    assert proc.returncode == 0
    assert HINT_SUBSTR["Bash"] in proc.stderr  # hint still keyed off tool name
    rec = read_audit(tmp_path)[0]
    # Serialized form of {"code": 1}; key/value survive the round-trip.
    assert json.loads(rec["error"]) == {"code": 1}


def test_error_truncated_to_500_chars(tmp_path):
    """Error strings are truncated to 500 chars before being recorded."""
    proc = run_hook({"tool_name": "Bash", "tool_error": "A" * 600}, tmp_path)
    assert proc.returncode == 0
    assert len(read_audit(tmp_path)[0]["error"]) == 500


def test_missing_error_records_empty_string(tmp_path):
    """No error field at all -> error recorded as empty string, still exit 0."""
    proc = run_hook({"tool_name": "Bash"}, tmp_path)
    assert proc.returncode == 0
    assert HINT_SUBSTR["Bash"] in proc.stderr
    assert read_audit(tmp_path)[0]["error"] == ""


@pytest.mark.parametrize("raw", ["", "   ", "{bad json", "not json at all", "[1,2,"])
def test_malformed_or_empty_stdin_is_graceful_noop(raw, tmp_path):
    """Empty/malformed stdin: graceful no-op — exit 0, no hint, no audit file."""
    proc = run_hook(raw, tmp_path)
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert "fenrir triage" not in proc.stderr
    # Early exit happens before the audit write, so nothing is created.
    assert read_audit(tmp_path) == []


def test_appends_across_invocations(tmp_path):
    """Multiple failures accumulate (append mode), not overwrite."""
    run_hook({"tool_name": "Bash", "tool_error": "first"}, tmp_path)
    run_hook({"tool_name": "Edit", "tool_error": "second"}, tmp_path)
    records = read_audit(tmp_path)
    assert [r["tool"] for r in records] == ["Bash", "Edit"]
    assert [r["error"] for r in records] == ["first", "second"]
