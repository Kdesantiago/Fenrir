#!/usr/bin/env python3
"""fenrir — PostToolUse(Bash): on branch-create, remind to plan on the board first. ADVISORY.

Fenrir's doctrine is plan-first: work starts on the board (Epic → Feature → atomic US), not in
the editor — so every commit is traced from the first one. The natural moment a developer skips
that is right when they spin up a feature branch and start coding. This hook fires after a
`git checkout -b` / `git switch -c` (a new branch), checks whether the session is already traced
to a User Story, and if NOT nudges them to run `/fenrir:plan` before writing code. If a plan
already exists it stays silent — no nagging.

PostToolUse cannot block (the branch is already created), and we never want to: this is advice,
not a gate. The engine's own gates (tracking-guard / delivery-trace CI) are the real floor. So:
exit 0 on EVERY path, fail-open on any error (junk stdin, no engine, no dashboard, check errors),
`FENRIR_TRACK_DISABLE=1` → silent exit 0. Pure stdlib.
"""
import json
import os
import re
import subprocess
import sys

# new feature branch: `git checkout -b <name>`, `git switch -c <name>`, `git switch --create <name>`.
# `_OPT` swallows leading git/subcommand options — a flag and, for `-c key=val` style, its value
# token — so global config flags don't hide the create.
_OPT = r"(?:-[^\s]+(?:\s+[^\s-][^\s]*)?\s+)*"
IS_NEW_BRANCH = re.compile(
    rf"\bgit\s+{_OPT}(?:checkout\s+{_OPT}-b|switch\s+{_OPT}(?:-c|--create))\b",
    re.IGNORECASE,
)


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
    if not isinstance(cmd, str) or not IS_NEW_BRANCH.search(cmd):
        sys.exit(0)  # only creating a new branch triggers the reminder
    session = (data.get("session_id") or "").strip()
    if not session:
        sys.exit(0)  # no session → don't nudge against unrelated active-US state
    engine = _engine()
    if not engine:
        sys.exit(0)
    # already planned? `check` exits 0 when traced / a US is active (also fail-open 0 when there's
    # no dashboard), 3 when untraced. Only nudge on a definite untraced (rc 3); anything else stays
    # silent so we never nag when a plan exists or when tracking can't be resolved.
    try:
        chk = subprocess.run([sys.executable, engine, "check", "--session", session],
                             capture_output=True, text=True, timeout=20)
    except Exception:
        sys.exit(0)
    if chk.returncode != 3:
        sys.exit(0)
    print(json.dumps({
        "systemMessage": "🧭 New branch, no board plan yet — run `/fenrir:plan` to decompose this "
                         "into a Feature + atomic User Stories before coding, so the work is "
                         "tracked from the first commit.",
        "suppressOutput": True}))
    sys.exit(0)


if __name__ == "__main__":
    main()
