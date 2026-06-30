"""Coverage for `scripts/migrate-tracking-hooks.py` — the one-shot cleaner that strips the
now-plugin-level tracking hooks from a repo's `.claude/settings.json`.

Asserts: removes the 5 tracking entries (shell-string AND exec-form), keeps every enforcement
hook (incl. tracking-guard), drops events left empty, is idempotent on a clean file, and is a
fail-safe no-op when the file is absent.

The migration script lives outside the dashboard package, so it is loaded by file path.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATE = _REPO_ROOT / "scripts" / "migrate-tracking-hooks.py"


def _load_migrate():
    spec = importlib.util.spec_from_file_location("migrate_tracking_under_test", _MIGRATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cmd(script: str) -> dict:
    return {"type": "command",
            "command": f"python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/{script}\""}


def _exec(script: str) -> dict:
    return {"type": "command", "command": "python",
            "args": [f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{script}"]}


def _stale_settings() -> dict:
    """A pre-migration settings.json: tracking entries co-located with enforcement ones, plus an
    event (SubagentStop) whose ONLY hook is tracking (must be dropped entirely)."""
    return {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [_cmd("prompt-guard.py"), _cmd("tracking-open.py")]}
            ],
            "PostToolUse": [
                {"matcher": "Bash",
                 "hooks": [_cmd("tracking-attribute.py"), _cmd("branch-plan-check.py")]}
            ],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [_cmd("tracking-guard.py")]}  # enforcement -> KEPT
            ],
            "Stop": [{"hooks": [_cmd("doc-staleness.py"), _cmd("tracking-finalize.py")]}],
            "SessionEnd": [{"hooks": [_cmd("session-end.py"), _exec("tracking-finalize.py")]}],
            "SubagentStop": [{"hooks": [_cmd("tracking-collect.py")]}],  # whole event -> DROPPED
            "PreCompact": [{"hooks": [_exec("precompact-focus.py")]}],   # whole event -> DROPPED
        }
    }


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / ".claude" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def _commands(data: dict) -> str:
    return json.dumps(data)


def test_removes_the_five_tracking_keeps_enforcement(tmp_path):
    mig = _load_migrate()
    path = _write(tmp_path, _stale_settings())
    summary = mig.migrate(str(path))
    assert summary["changed"] is True

    after = json.loads(path.read_text(encoding="utf-8"))
    blob = _commands(after)
    for gone in ("tracking-open.py", "tracking-collect.py", "tracking-attribute.py",
                 "tracking-finalize.py", "precompact-focus.py"):
        assert gone not in blob
    # enforcement (incl. tracking-guard) preserved
    for kept in ("prompt-guard.py", "branch-plan-check.py", "tracking-guard.py",
                 "doc-staleness.py", "session-end.py"):
        assert kept in blob
    # events whose only hook was tracking are dropped; mixed events keep their non-tracking hooks
    hooks = after["hooks"]
    assert "SubagentStop" not in hooks and "PreCompact" not in hooks
    assert set(summary["emptied_events"]) == {"SubagentStop", "PreCompact"}
    assert hooks["UserPromptSubmit"][0]["hooks"] == [_cmd("prompt-guard.py")]
    assert hooks["PostToolUse"][0]["hooks"] == [_cmd("branch-plan-check.py")]
    assert hooks["PreToolUse"][0]["hooks"] == [_cmd("tracking-guard.py")]


def test_idempotent_on_clean_file(tmp_path):
    mig = _load_migrate()
    path = _write(tmp_path, _stale_settings())
    mig.migrate(str(path))            # first pass cleans
    cleaned = path.read_text(encoding="utf-8")
    second = mig.migrate(str(path))   # second pass: nothing to do
    assert second["changed"] is False
    assert path.read_text(encoding="utf-8") == cleaned  # byte-stable, no rewrite churn


def test_clean_settings_untouched(tmp_path):
    mig = _load_migrate()
    clean = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [_cmd("tracking-guard.py")]}]},
             "permissions": {"allow": ["Bash"]}}
    path = _write(tmp_path, clean)
    summary = mig.migrate(str(path))
    assert summary["changed"] is False
    assert json.loads(path.read_text(encoding="utf-8")) == clean  # other keys preserved verbatim


def test_no_file_is_fail_safe_noop(tmp_path):
    mig = _load_migrate()
    summary = mig.migrate(str(tmp_path / ".claude" / "settings.json"))
    assert summary["changed"] is False
    assert "reason" in summary


def test_main_exits_zero_and_uses_argv_root(tmp_path, capsys):
    mig = _load_migrate()
    _write(tmp_path, _stale_settings())
    rc = mig.main(["migrate-tracking-hooks.py", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["changed"] is True


def test_main_fail_safe_zero_when_no_repo(tmp_path):
    mig = _load_migrate()
    rc = mig.main(["migrate-tracking-hooks.py", str(tmp_path / "does-not-exist")])
    assert rc == 0


@pytest.mark.parametrize("script", [
    "tracking-open.py", "tracking-collect.py", "tracking-attribute.py",
    "tracking-finalize.py", "precompact-focus.py",
])
def test_detects_both_command_and_exec_forms(script):
    mig = _load_migrate()
    assert mig._references_tracking(_cmd(script)) is True
    assert mig._references_tracking(_exec(script)) is True


def test_does_not_flag_tracking_guard():
    mig = _load_migrate()
    assert mig._references_tracking(_cmd("tracking-guard.py")) is False
