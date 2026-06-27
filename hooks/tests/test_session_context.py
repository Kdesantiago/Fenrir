"""Tests for the Fenrir SessionStart context-injector hook.

Subprocess-based: the hook is invoked as a real process with JSON piped to
stdin, and we assert on the observed exit code + stdout JSON. All side-effect
inputs (org-profile.yaml, stack-interface.yaml, gate-exceptions.jsonl) live
under a per-test tmp_path that we point CLAUDE_PROJECT_DIR at, so nothing
touches the real repo.

Contract (validated against the real hook):
  - SessionStart hook. Always exits 0 (fail-OPEN).
  - When there is nothing to inject -> exits 0 with EMPTY stdout (silent).
  - When there IS something to inject -> prints one JSON object:
      {"hookSpecificOutput": {"hookEventName": "SessionStart",
                              "additionalContext": "<bulleted text>"}}
  - The hook does NOT read stdin: malformed/empty stdin is irrelevant to the
    decision; behavior depends purely on the project files. We still feed
    stdin to prove it is ignored gracefully (exit 0 either way).

stdlib + pytest only.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session-context.py"


# --------------------------------------------------------------------------
# helpers (kept inside this file; no shared conftest / __init__)
# --------------------------------------------------------------------------
def run_hook(project_dir: Path, stdin: str = "{}"):
    """Run the hook with project_dir as CLAUDE_PROJECT_DIR. Returns CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env={"CLAUDE_PROJECT_DIR": str(project_dir)},
    )


def parse_output(proc):
    """Parse stdout as the hook's hookSpecificOutput JSON and return additionalContext."""
    payload = json.loads(proc.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    return payload["hookSpecificOutput"]["additionalContext"]


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# --------------------------------------------------------------------------
# no-op / silent paths (fail-OPEN: exit 0, empty stdout)
# --------------------------------------------------------------------------
def test_empty_project_is_silent_exit0(tmp_path):
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


@pytest.mark.parametrize("stdin", ["", "not json at all{{{", "garbage", '{"some":"event"}'])
def test_malformed_or_empty_stdin_is_ignored_silent_on_empty_project(tmp_path, stdin):
    # The hook never reads stdin; on an empty project it must still be a silent no-op.
    proc = run_hook(tmp_path, stdin=stdin)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_malformed_stdin_still_emits_when_project_has_profile(tmp_path):
    # Proves stdin content is irrelevant: garbage stdin + a real profile -> context emitted.
    write(tmp_path / "org-profile.yaml", "platform: aks\n")
    proc = run_hook(tmp_path, stdin="totally not json")
    assert proc.returncode == 0
    ctx = parse_output(proc)
    assert "platform=aks" in ctx


# --------------------------------------------------------------------------
# org-profile.yaml injection
# --------------------------------------------------------------------------
def test_org_profile_emits_delivery_contract(tmp_path):
    write(tmp_path / "org-profile.yaml", "platform: aks\nframework: fastapi\n")
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    ctx = parse_output(proc)
    assert "DELIVERY CONTRACT (org-profile.yaml)" in ctx
    assert "platform=aks" in ctx
    assert "framework=fastapi" in ctx
    assert "Generators must match this stack or refuse." in ctx


def test_org_profile_only_known_keys_in_declared_order(tmp_path):
    # Unknown keys are dropped; known keys appear in the hook's fixed order.
    write(
        tmp_path / "org-profile.yaml",
        "framework: fastapi\nplatform: aks\nbogus: nope\nllm_provider: anthropic\n",
    )
    ctx = parse_output(run_hook(tmp_path))
    assert "bogus" not in ctx
    # hook order: platform, framework, ..., llm_provider
    assert ctx.index("platform=aks") < ctx.index("framework=fastapi") < ctx.index("llm_provider=anthropic")


# --------------------------------------------------------------------------
# stack-interface.yaml injection
# --------------------------------------------------------------------------
def test_stack_interface_emits_wrappers_excluding_name_version(tmp_path):
    write(tmp_path / "stack-interface.yaml", "name: foo\nversion: 1\ndeploy: wrapper-deploy\n")
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    ctx = parse_output(proc)
    assert "STACK INTERFACE active" in ctx
    assert "deploy=wrapper-deploy" in ctx
    # name/version are filtered out of the wrapper list
    assert "name=foo" not in ctx
    assert "version=1" not in ctx
    assert "stack-adapter agent" in ctx


def test_stack_interface_with_only_name_version_emits_nothing(tmp_path):
    # File exists but contributes no wrappers -> no part -> silent.
    write(tmp_path / "stack-interface.yaml", "name: foo\nversion: 1\n")
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


# --------------------------------------------------------------------------
# gate-exceptions.jsonl injection
# --------------------------------------------------------------------------
EXC = "docs/delivery-memory/gate-exceptions.jsonl"


def test_open_future_exception_is_injected(tmp_path):
    write(
        tmp_path / EXC,
        json.dumps({"rule": "coverage", "status": "open", "expires": "2099-01-01", "granted_by": "alice"}) + "\n",
    )
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    ctx = parse_output(proc)
    assert "OPEN GATE-EXCEPTIONS (1)" in ctx
    assert "coverage (until 2099-01-01, by alice)" in ctx


@pytest.mark.parametrize(
    "record,reason",
    [
        ({"rule": "r", "status": "open", "expires": "2000-01-01", "granted_by": "a"}, "past expiry"),
        ({"rule": "r", "status": "closed", "expires": "2099-01-01", "granted_by": "a"}, "closed status"),
        ({"rule": "r", "status": "open", "granted_by": "a"}, "missing expiry treated as expired"),
        ({"rule": "r", "status": "open", "expires": "not-a-date", "granted_by": "a"}, "unparseable expiry"),
    ],
)
def test_non_active_exceptions_are_excluded(tmp_path, record, reason):
    write(tmp_path / EXC, json.dumps(record) + "\n")
    proc = run_hook(tmp_path)
    assert proc.returncode == 0, reason
    assert proc.stdout.strip() == "", reason


def test_missing_gate_exceptions_file_is_silent(tmp_path):
    # No file at all -> FileNotFoundError swallowed -> silent no-op.
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_exception_count_reflects_only_active_rows(tmp_path):
    rows = [
        {"rule": "open1", "status": "open", "expires": "2099-01-01", "granted_by": "a"},
        {"rule": "expired", "status": "open", "expires": "2000-01-01", "granted_by": "b"},
        {"rule": "open2", "status": "open", "expires": "2099-02-02", "granted_by": "c"},
    ]
    write(tmp_path / EXC, "\n".join(json.dumps(r) for r in rows) + "\n")
    ctx = parse_output(run_hook(tmp_path))
    assert "OPEN GATE-EXCEPTIONS (2)" in ctx
    assert "open1" in ctx and "open2" in ctx
    assert "expired" not in ctx


# --------------------------------------------------------------------------
# combined: all three sources produce three bullet parts
# --------------------------------------------------------------------------
def test_all_three_sources_combine(tmp_path):
    write(tmp_path / "org-profile.yaml", "platform: aks\n")
    write(tmp_path / "stack-interface.yaml", "name: x\ndeploy: w\n")
    write(
        tmp_path / EXC,
        json.dumps({"rule": "r", "status": "open", "expires": "2099-01-01", "granted_by": "bob"}) + "\n",
    )
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    ctx = parse_output(proc)
    assert ctx.count("•") == 3  # three bullet points
    assert "DELIVERY CONTRACT" in ctx
    assert "STACK INTERFACE active" in ctx
    assert "OPEN GATE-EXCEPTIONS (1)" in ctx


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
