"""Tests for subject-focused compaction: the engine `focus` command, the PreCompact hook
(precompact-focus.py) that snapshots the dev subject, and session-context.py re-injecting it on
SessionStart(source=compact). Self-contained (subprocess, stdlib), isolated via CLAUDE_PROJECT_DIR.

PreCompact can't steer the summary text, so the design is: snapshot before compaction →
re-inject after. These tests prove both halves and that startup sessions are NOT re-seeded."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "scripts" / "track_session.py"
PRECOMPACT = ROOT / "hooks" / "precompact-focus.py"
SESSION_CTX = ROOT / "hooks" / "session-context.py"


def _env(project_dir, **extra):
    e = {"CLAUDE_PROJECT_DIR": str(project_dir), "PATH": "/usr/bin:/bin"}
    e.update({k: v for k, v in extra.items() if v is not None})
    return e


def _run(target, stdin_text, project_dir, *args, **extra):
    return subprocess.run([sys.executable, str(target), *args], input=stdin_text,
                          capture_output=True, text=True,
                          env=_env(project_dir, **extra), cwd=str(project_dir))


def _focus_file(project_dir):
    return Path(project_dir) / ".claude" / "tracking" / "compact-focus.md"


# --------------------------------------------------------------------- engine `focus`
def test_engine_focus_writes_snapshot_from_active_us(tmp_path):
    # no dashboard needed: set-us records the active US, focus snapshots it
    _run(ENGINE, "", tmp_path, "set-us", "--id", "us-42", "--session", "s1")
    p = _run(ENGINE, "", tmp_path, "focus", "--session", "s1", "--trigger", "auto")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["tracking"] == "focus" and out["us_id"] == "us-42"
    f = _focus_file(tmp_path)
    assert f.exists()
    body = f.read_text()
    assert "Active development subject" in body and "us-42" in body


# --------------------------------------------------------------------- PreCompact hook
def test_precompact_hook_snapshots_and_allows(tmp_path):
    _run(ENGINE, "", tmp_path, "set-us", "--id", "us-7", "--session", "sC")
    stdin = json.dumps({"session_id": "sC", "hook_event_name": "PreCompact",
                        "compaction_trigger": "auto", "custom_instructions": ""})
    p = _run(PRECOMPACT, stdin, tmp_path)
    assert p.returncode == 0  # never blocks compaction
    assert _focus_file(tmp_path).exists()
    if p.stdout.strip():  # surfaces the subject, does not block
        out = json.loads(p.stdout)
        assert "decision" not in out  # allow, never block
        assert "us-7" in out.get("systemMessage", "")


def test_precompact_hook_survives_junk(tmp_path):
    p = _run(PRECOMPACT, "}{ not json", tmp_path)
    assert p.returncode == 0
    assert not _focus_file(tmp_path).exists()


def test_precompact_hook_disabled_env(tmp_path):
    _run(ENGINE, "", tmp_path, "set-us", "--id", "us-7", "--session", "sC")
    stdin = json.dumps({"session_id": "sC", "compaction_trigger": "manual"})
    p = _run(PRECOMPACT, stdin, tmp_path, FENRIR_TRACK_DISABLE="1")
    assert p.returncode == 0
    assert not _focus_file(tmp_path).exists()


# --------------------------------------------------- session-context re-injection
def test_session_context_reinjects_focus_on_compact(tmp_path):
    f = _focus_file(tmp_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("# Active development subject (compaction focus)\n**Working on:** `us-99` — thing\n")
    p = _run(SESSION_CTX, json.dumps({"source": "compact"}), tmp_path)
    assert p.returncode == 0
    out = json.loads(p.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "RESUMING AFTER COMPACTION" in ctx and "us-99" in ctx


def test_session_context_no_focus_on_startup(tmp_path):
    f = _focus_file(tmp_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("# focus\n**Working on:** `us-99`\n")
    # startup (not compact) + no org-profile here → nothing to inject → silent exit 0
    p = _run(SESSION_CTX, json.dumps({"source": "startup"}), tmp_path)
    assert p.returncode == 0
    assert "us-99" not in (p.stdout or "")
