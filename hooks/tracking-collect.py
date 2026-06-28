#!/usr/bin/env python3
"""fenrir — SubagentStop: ledger a finished subagent run for precise cost attribution.

When a subagent finishes, record its run so the delivery-tracker can later attribute that
run's real cost to the right User Story (`cli attribute --run`). Thin, deterministic wrapper
around scripts/track_session.py. Non-blocking, fail-open: any trouble → exit 0 silently.

SubagentStop payload fields vary; we use session_id plus whatever identifies the run
(run_id / agent_id / subagent_type / transcript_path basename as a last resort).
Pure stdlib.
"""
import json
import os
import subprocess
import sys


def _engine() -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    # plugin layout: scripts/ next to hooks/ ; consuming-repo layout: .claude/hooks/ + .claude/scripts/
    for cand in (os.path.join(root, "scripts", "track_session.py"),
                 os.path.join(root, ".claude", "scripts", "track_session.py"),
                 os.path.join(os.path.dirname(__file__), "..", "scripts", "track_session.py")):
        if os.path.exists(cand):
            return cand
    return ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    session = data.get("session_id", "") or ""
    if not session:
        sys.exit(0)
    run = (data.get("run_id") or data.get("agent_id") or "").strip()
    if not run:
        tp = data.get("transcript_path") or ""
        if tp:
            run = os.path.splitext(os.path.basename(tp))[0]
    if not run:
        sys.exit(0)
    stype = data.get("subagent_type") or data.get("agent_type") or ""
    engine = _engine()
    if not engine:
        sys.exit(0)
    try:
        subprocess.run([sys.executable, engine, "collect-run", "--session", session,
                        "--run", run, "--type", stype],
                       capture_output=True, text=True, timeout=15)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
