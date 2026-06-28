#!/usr/bin/env python3
"""fenrir — PreCompact: snapshot the current dev subject so compaction stays on-topic.

The user's intent: when context is compacted (auto near the limit, or manual `/compact`), the
summary should serve the DEVELOPMENT IN PROGRESS — not be a flat global recap. A PreCompact hook
cannot edit the summary text (it is decision-only). So this hook captures the subject BEFORE the
transcript is compacted — the active US (goal/acceptance), its feature+epic, and live git context
(branch, recent commits, in-flight files) — into a focus file. Its twin, `session-context.py`,
re-injects that focus on the next SessionStart (source=compact), re-grounding the compacted
session on exactly what you were building.

Thin wrapper around scripts/track_session.py `focus`. Allows compaction (never blocks),
non-blocking, fail-open. Pure stdlib.
"""
import json
import os
import subprocess
import sys


def _engine() -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    for cand in (os.path.join(root, "scripts", "track_session.py"),
                 os.path.join(root, ".claude", "scripts", "track_session.py"),
                 os.path.join(os.path.dirname(__file__), "..", "scripts", "track_session.py")):
        if os.path.exists(cand):
            return cand
    return ""


def main() -> None:
    if os.environ.get("FENRIR_TRACK_DISABLE") == "1":
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    session = (data.get("session_id") or "").strip()
    trigger = data.get("compaction_trigger") or data.get("trigger") or "manual"
    instructions = (data.get("custom_instructions") or "").strip()
    engine = _engine()
    if not engine:
        sys.exit(0)
    args = [sys.executable, engine, "focus", "--trigger", str(trigger)]
    if session:
        args += ["--session", session]
    if instructions:
        args += ["--instructions", instructions]
    subject = ""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=20)
        out = (r.stdout or "").strip()
        if out:
            subject = (json.loads(out) or {}).get("subject", "")
    except Exception:
        pass
    # Surface the focus to the user; do NOT block compaction.
    if subject:
        print(json.dumps({
            "systemMessage": f"🧭 Compaction focused on the active work: {subject}. "
                             "The summary will be re-grounded on it after compaction.",
            "suppressOutput": True}))
    sys.exit(0)


if __name__ == "__main__":
    main()
