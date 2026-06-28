#!/usr/bin/env python3
"""fenrir — SessionEnd: auto-attribute the session's real cost to its User Story.

The "automatic" half of automatic+mandatory tracking. On session end, ensure an active US
exists for the session and charge the session's real token/USD cost to it (whole-session
`link`, captured from telemetry). Deterministic, non-blocking, fail-open — never breaks the
session. Runs ALONGSIDE the existing session-end.py (delivery-memory housekeeping).

The deterministic floor only guarantees attribution to a (possibly catch-all) US. The
delivery-tracker SUBAGENT does the smart re-parenting/titling. Pure stdlib.
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
        data = {}
    session = (data.get("session_id") or "").strip()
    engine = _engine()
    if not engine:
        sys.exit(0)
    args = [sys.executable, engine, "finalize"]
    if session:
        args += ["--session", session]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=45)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
