#!/usr/bin/env python3
"""fenrir — PreToolUse: make tracing a commit obligatory.

A skill cannot force tracking; this hook can. On `git commit`, it ensures the work is traced
to a User Story on the board. Two modes (env `FENRIR_TRACK_ENFORCE`):

  • default ("auto") — AUTOMATIC: if untraced, auto-create a catch-all US for the session,
    then ALLOW the commit. Tracking always happens; the commit is never blocked. This is the
    safe default (it cannot brick a session) and matches Fenrir's "advice = fast feedback".
  • "strict"        — OBLIGATORY: if untraced AND a US cannot be auto-created, DENY the commit
    with instructions. The authoritative gate is still CI (`delivery-trace`) + branch-protection.

Scoped to `git commit` only (NOT every Bash/Write) so normal work is never slowed or blocked.
FAIL-OPEN: no dashboard, parse error, engine missing → ALLOW. Runs alongside delivery-guard.py
(most-restrictive decision wins, so this allowing never overrides delivery-guard's deny).

Decision contract (PreToolUse): print JSON, exit 0. permissionDecision: deny | ask | allow.
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
    for cand in (os.path.join(root, "scripts", "track_session.py"),
                 os.path.join(root, ".claude", "scripts", "track_session.py"),
                 os.path.join(os.path.dirname(__file__), "..", "scripts", "track_session.py")):
        if os.path.exists(cand):
            return cand
    return ""


def decide(kind: str, reason: str = "") -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": kind,
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def _run(engine: str, *args: str):
    return subprocess.run([sys.executable, engine, *args],
                          capture_output=True, text=True, timeout=30)


def main() -> None:
    if os.environ.get("FENRIR_TRACK_DISABLE") == "1":
        decide("allow")
    try:
        data = json.load(sys.stdin)
    except Exception:
        decide("allow")  # can't parse → don't interfere
    if data.get("tool_name") != "Bash":
        decide("allow")
    cmd = (data.get("tool_input", {}) or {}).get("command", "")
    if not isinstance(cmd, str) or not IS_COMMIT.search(cmd) or IS_AMEND.search(cmd):
        decide("allow")  # only gate real commits

    session = (data.get("session_id") or "").strip()
    engine = _engine()
    if not engine:
        decide("allow", "tracking engine not found — allowing (fail-open)")
    strict = os.environ.get("FENRIR_TRACK_ENFORCE", "auto").lower() == "strict"

    try:
        chk = _run(engine, "check", "--session", session)
    except Exception:
        decide("allow", "tracking check errored — allowing (fail-open)")

    if chk.returncode == 0:
        decide("allow")  # already traced (or no dashboard → fail-open inside the engine)

    # untraced, and the board IS reachable (else check would have failed-open to rc 0).
    if strict:
        # OBLIGATORY: force a deliberate US — do not auto-create, deny the commit.
        decide("deny", "This commit is not traced to a User Story (FENRIR_TRACK_ENFORCE=strict). "
               "Create/select the US first — delegate to the delivery-tracker subagent or run the "
               "dashboard board CLI — then reference it (e.g. 'us-42') and commit.")

    # AUTOMATIC (default): auto-create a catch-all US so nothing is ever untracked, then allow.
    try:
        ens = _run(engine, "ensure-us", "--session", session)
        ok = ens.returncode == 0 and '"tracking": "skipped"' not in (ens.stdout or "")
    except Exception:
        ok = False
    if ok:
        decide("allow", "auto-created a User Story for this work — commit traced "
               "(let the delivery-tracker subagent re-title/re-parent it).")
    decide("allow", "could not auto-create a US — allowing (fail-open).")


if __name__ == "__main__":
    main()
