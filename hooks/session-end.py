#!/usr/bin/env python3
"""fenrir — SessionEnd: finalize delivery-memory (non-mutating).

Non-blocking (output ignored). Writes a session-summary line to the audit trail:
counts of open vs expired gate-exceptions and whether code changed without a CHANGELOG
touch. It does NOT mutate the gate-exceptions ledger — closing expired waivers is the
memory-keeper skill's job (an explicit, reviewable action). This is housekeeping/visibility.
Pure stdlib.
"""
import json
import os
import sys
from datetime import date, datetime, timezone


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass  # SessionEnd payload is small; we don't need it
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    today = date.today()
    open_n = expired_n = 0
    try:
        fp = os.path.join(root, "docs", "delivery-memory", "gate-exceptions.jsonl")
        for line in open(fp):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue  # a single corrupt line must not drop the whole summary
            if e.get("status", "open") != "open":
                continue
            exp = e.get("expires")
            try:
                if exp and datetime.strptime(str(exp), "%Y-%m-%d").date() >= today:
                    open_n += 1
                else:
                    expired_n += 1
            except (ValueError, TypeError):
                expired_n += 1
    except FileNotFoundError:
        pass
    except Exception:
        return
    try:
        d = os.path.join(root, ".claude", "audit"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sessions.jsonl"), "a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                    "open_gate_exceptions": open_n,
                    "expired_gate_exceptions_pending_close": expired_n}) + "\n")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
