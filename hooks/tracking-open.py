#!/usr/bin/env python3
"""fenrir — UserPromptSubmit: open/ensure the session's User Story automatically.

The "automatic US" half of mandatory tracking. On every user prompt it ensures a User Story
exists for the session (creating a catch-all under an `Auto-tracked sessions` epic if none),
so work is tracked from the first message — no `git commit`, no manual CLI. Injects the active
US id back into the session as context so the model can reference it.

Non-blocking, fail-open: no dashboard / any error → exit 0 silently (never blocks a prompt).
Pure stdlib.
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
    engine = _engine()
    if not engine:
        sys.exit(0)
    try:
        r = subprocess.run([sys.executable, engine, "ensure-us", "--session", session],
                           capture_output=True, text=True, timeout=30)
        out = json.loads((r.stdout or "{}").strip().splitlines()[-1])
    except Exception:
        sys.exit(0)
    us = out.get("us_id")
    if us and out.get("tracking") in ("ensured", "active"):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"DELIVERY TRACKING active — this session's work is being "
            f"tracked on User Story {us}. Attribute distinct sub-tasks to their own US with "
            f"`scripts/track_session.py set-us --id <us> --session {session}` before delegating."}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
