"""Tests for the Fenrir SessionEnd hook (hooks/session-end.py).

This hook is NON-BLOCKING: Claude Code ignores its output. It always exits 0,
never writes to stdout, and its sole side effect is appending ONE summary line
to <project>/.claude/audit/sessions.jsonl. The summary counts open vs. expired
gate-exceptions read from <project>/docs/delivery-memory/gate-exceptions.jsonl.

All assertions below were validated against the real hook by piping crafted
stdin and observing actual exit code / stdout / written files.

stdlib + pytest only. Self-contained: no conftest.py / __init__.py.
"""
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session-end.py"

AUDIT_REL = Path(".claude") / "audit" / "sessions.jsonl"
LEDGER_REL = Path("docs") / "delivery-memory" / "gate-exceptions.jsonl"


def run_hook(stdin_text, project_dir):
    """Invoke the hook as a subprocess with stdin piped in.

    Returns the CompletedProcess. CLAUDE_PROJECT_DIR is pointed at the
    isolated tmp dir so the real repo is never touched.
    """
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
        text=True,
        capture_output=True,
        cwd=str(project_dir),
        env={"CLAUDE_PROJECT_DIR": str(project_dir), "PATH": ""},
    )


def read_audit(project_dir):
    """Return parsed audit lines (list of dicts). Empty list if file absent."""
    fp = Path(project_dir) / AUDIT_REL
    if not fp.exists():
        return []
    return [json.loads(ln) for ln in fp.read_text().splitlines() if ln.strip()]


def write_ledger(project_dir, lines):
    fp = Path(project_dir) / LEDGER_REL
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("\n".join(lines) + ("\n" if lines else ""))


# --- Output contract: always exit 0, never any stdout -----------------------


@pytest.mark.parametrize(
    "stdin_text",
    [
        '{"hook_event_name":"SessionEnd"}',  # well-formed payload
        '{}',                                 # empty object
        '',                                   # empty stdin
        'not json at all {{{',                # malformed / non-JSON
        '[1, 2, 3]',                          # valid JSON, wrong shape
    ],
    ids=["wellformed", "empty_obj", "empty_stdin", "malformed", "wrong_shape"],
)
def test_always_exit_zero_no_stdout(tmp_path, stdin_text):
    """Non-blocking hook: every input yields exit 0 and silent stdout."""
    res = run_hook(stdin_text, tmp_path)
    assert res.returncode == 0, res.stderr
    assert res.stdout == ""


# --- Side effect: audit line is always appended -----------------------------


def test_appends_audit_line_with_no_ledger(tmp_path):
    """With no gate-exceptions ledger, the hook still writes one audit line
    with zero counts (FileNotFoundError is swallowed)."""
    res = run_hook('{"hook_event_name":"SessionEnd"}', tmp_path)
    assert res.returncode == 0
    lines = read_audit(tmp_path)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["open_gate_exceptions"] == 0
    assert entry["expired_gate_exceptions_pending_close"] == 0
    assert "ts" in entry
    # ts must be a parseable ISO timestamp
    datetime.fromisoformat(entry["ts"])


def test_audit_written_even_on_malformed_stdin(tmp_path):
    """Fail-open: malformed stdin does not suppress the housekeeping summary."""
    res = run_hook('garbage}{', tmp_path)
    assert res.returncode == 0
    assert len(read_audit(tmp_path)) == 1


def test_audit_appends_not_overwrites(tmp_path):
    """Two invocations produce two audit lines (append mode)."""
    run_hook('{}', tmp_path)
    run_hook('{}', tmp_path)
    assert len(read_audit(tmp_path)) == 2


# --- Counting logic: open vs. expired gate-exceptions -----------------------


def test_counts_open_vs_expired(tmp_path):
    """Mixed ledger: open-future and open-today count as open; past/closed/
    missing-expires/bad-date resolve per the hook's rules. Corrupt JSON lines
    and the closed entry are excluded."""
    today = date.today()
    future = (today + timedelta(days=365)).isoformat()
    past = (today - timedelta(days=365)).isoformat()
    write_ledger(
        tmp_path,
        [
            json.dumps({"status": "open", "expires": future}),       # open
            json.dumps({"status": "open", "expires": today.isoformat()}),  # open (>= today)
            json.dumps({"status": "open", "expires": past}),         # expired
            json.dumps({"status": "closed", "expires": future}),     # skipped
            json.dumps({"status": "open"}),                          # expired (no expires)
            json.dumps({"status": "open", "expires": "not-a-date"}), # expired (bad date)
            "this is not valid json",                                # skipped
            "",                                                       # skipped (blank)
        ],
    )
    res = run_hook('{"hook_event_name":"SessionEnd"}', tmp_path)
    assert res.returncode == 0
    entry = read_audit(tmp_path)[0]
    assert entry["open_gate_exceptions"] == 2
    assert entry["expired_gate_exceptions_pending_close"] == 3


def test_expires_today_counts_as_open(tmp_path):
    """Boundary: expires == today is still open (comparison is >= today)."""
    write_ledger(tmp_path, [json.dumps({"status": "open", "expires": date.today().isoformat()})])
    run_hook('{}', tmp_path)
    entry = read_audit(tmp_path)[0]
    assert entry["open_gate_exceptions"] == 1
    assert entry["expired_gate_exceptions_pending_close"] == 0


def test_missing_status_defaults_to_open(tmp_path):
    """An entry with no 'status' key defaults to 'open' (status.get default)."""
    future = (date.today() + timedelta(days=30)).isoformat()
    write_ledger(tmp_path, [json.dumps({"expires": future})])
    run_hook('{}', tmp_path)
    entry = read_audit(tmp_path)[0]
    assert entry["open_gate_exceptions"] == 1
    assert entry["expired_gate_exceptions_pending_close"] == 0


def test_corrupt_lines_do_not_drop_summary(tmp_path):
    """A single corrupt JSON line is skipped but valid lines still counted and
    the summary is still emitted."""
    future = (date.today() + timedelta(days=30)).isoformat()
    write_ledger(
        tmp_path,
        ["{ broken", json.dumps({"status": "open", "expires": future}), "also broken {"],
    )
    run_hook('{}', tmp_path)
    entry = read_audit(tmp_path)[0]
    assert entry["open_gate_exceptions"] == 1
    assert entry["expired_gate_exceptions_pending_close"] == 0


# --- Isolation: real repo untouched ----------------------------------------


def test_does_not_touch_real_repo(tmp_path):
    """Sanity: writing happens under CLAUDE_PROJECT_DIR (tmp_path), so the
    audit file materializes inside tmp_path and nowhere else we can see."""
    run_hook('{}', tmp_path)
    assert (tmp_path / AUDIT_REL).exists()
