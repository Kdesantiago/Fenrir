#!/usr/bin/env python3
"""fenrir — config audit (security, ported from PAI ConfigAudit).

PostToolUse on Write/Edit. When .claude/settings.json changes, diff it against the last
snapshot and append an audit line; flag changes to sensitive keys (permissions/hooks/env/
mcpServers) — those alter how the gate itself behaves. Non-blocking, pure stdlib.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

SENSITIVE = {"permissions", "hooks", "env", "mcpServers", "allowedHttpHookUrls"}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name", "") not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)
    fp = (data.get("tool_input", {}) or {}).get("file_path", "") or ""
    # settings.json AND settings.local.json (the override an attacker would use to neuter hooks).
    if not re.search(r"(^|/)settings(\.local)?\.json$", fp):
        sys.exit(0)
    try:
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        audit = os.path.join(root, ".claude", "audit"); os.makedirs(audit, exist_ok=True)
        snap = os.path.join(audit, ".settings.snapshot.json")
        cur = json.load(open(fp)) if os.path.exists(fp) else {}
        prev = json.load(open(snap)) if os.path.exists(snap) else {}
        changed = sorted({k for k in set(cur) | set(prev) if cur.get(k) != prev.get(k)})
        if changed:
            with open(os.path.join(audit, "config-changes.jsonl"), "a") as f:
                f.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "session": data.get("session_id", ""),
                    "file": fp, "changed_keys": changed,
                    "sensitive": sorted(set(changed) & SENSITIVE),
                }) + "\n")
            json.dump(cur, open(snap, "w"))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
