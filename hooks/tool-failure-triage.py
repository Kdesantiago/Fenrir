#!/usr/bin/env python3
"""fenrir — PostToolUseFailure: failure triage trail.

Non-blocking. When a tool call fails, append it to an audit trail and print a short
triage hint so repeated failures are visible (a delivery-regression signal). Pure stdlib.

Contract (PostToolUseFailure): non-blocking — exit 0. Side effects only.
"""
import json
import os
import sys
from datetime import UTC, datetime

HINTS = {
    "Bash": "check the command's exit output; a gate hook may have denied it (see security-events.jsonl).",
    "Edit": "the old_string likely didn't match — re-read the file region before editing.",
    "Write": "path or permissions issue — confirm the directory exists and is writable.",
}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "")
    if not isinstance(tool, str):
        tool = ""
    # PostToolUseFailure is a documented event (code.claude.com/docs/en/hooks);
    # field name has varied across versions, so accept either.
    err = data.get("tool_error") or data.get("error") or ""
    err = (err if isinstance(err, str) else json.dumps(err))[:500]
    try:
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        d = os.path.join(root, ".claude", "audit"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "tool-failures.jsonl"), "a") as f:
            f.write(json.dumps({"ts": datetime.now(UTC).isoformat(),
                    "tool": tool, "error": err}) + "\n")
    except Exception:
        pass
    hint = HINTS.get(tool)
    if hint:
        sys.stderr.write(f"fenrir triage: {tool} failed — {hint}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
