#!/usr/bin/env python3
"""fenrir — PostToolUse(Bash): attribute the commit's cost to its User Story. AUTOMATIC + MANDATORY.

The missing half of per-US cost. `tracking-finalize` only runs at session end, so a whole
session's main-thread spend lumps onto ONE US. This hook fires after every `git commit` and
flushes the cost accrued SINCE THE LAST COMMIT to the US that commit delivers — so each US
carries its real, granular cost with zero manual steps. The commit is the unit of attribution:
"work since the previous commit → this commit's US".

The US is resolved by the engine: the `us-N` in the commit message (the delivery-trace gate
makes commits reference one), else the current active US, else a catch-all. Scoped to real
`git commit` (not --amend, not every Bash). Non-blocking, fail-open: any trouble → exit 0.
Pure stdlib.
"""
import json
import os
import re
import subprocess
import sys

IS_COMMIT = re.compile(r"\bgit\s+(?:-[^\s]+\s+)*commit\b", re.IGNORECASE)
IS_AMEND = re.compile(r"--amend", re.IGNORECASE)


def _engine() -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    # plugin layout: scripts/ next to hooks/ ; consuming-repo layout: .claude/scripts/
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
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input", {}) or {}).get("command", "")
    if not isinstance(cmd, str) or not IS_COMMIT.search(cmd) or IS_AMEND.search(cmd):
        sys.exit(0)  # only a real commit triggers attribution
    session = (data.get("session_id") or "").strip()
    engine = _engine()
    if not engine:
        sys.exit(0)
    args = [sys.executable, engine, "attribute-commit"]
    if session:
        args += ["--session", session]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=45)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
