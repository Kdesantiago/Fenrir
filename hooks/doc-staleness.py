#!/usr/bin/env python3
"""fenrir — Stop hook: docs-up-to-date backstop.

When a session ends, if code changed but CHANGELOG.md didn't, block the stop ONCE and
remind to sync docs (run the doc-keeper agent). Deterministic nudge behind the "docs
always up to date" goal — complements reviewer's "changelog entry present" merge check.

Contract (Stop): print JSON, exit 0.
  block once: {"decision":"block","reason":...}
  otherwise:  exit 0.
Loop-safe: if `stop_hook_active` is set (we already blocked this stop), do nothing.
Fail-OPEN.
"""
import json
import os
import re
import subprocess
import sys

CODE = re.compile(r"\.(py|ts|tsx|js|jsx|go|java|rb|rs|kt|cs|php|scala|swift)$", re.I)
TESTISH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)(test_|conftest)|(_test|\.test|\.spec)\.", re.I)


def _changed(root):
    files = set()
    for args in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]):
        try:
            r = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                files.update(x for x in r.stdout.splitlines() if x.strip())
        except Exception:
            return None  # can't tell → fail open
    return files


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("stop_hook_active"):
        sys.exit(0)  # already blocked once this stop — don't loop

    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    changed = _changed(root)
    if not changed:
        sys.exit(0)

    code_changed = any((CODE.search(f) or f.startswith("src/")) and not TESTISH.search(f) for f in changed)
    changelog_touched = any(os.path.basename(f) == "CHANGELOG.md" for f in changed)

    if code_changed and not changelog_touched:
        print(json.dumps({
            "decision": "block",
            "reason": "Code changed this session but CHANGELOG.md was not updated. Sync the docs before finishing: delegate to the doc-keeper agent (updates CHANGELOG + affected READMEs/API-docs to the diff), or add an [Unreleased] entry yourself. If the change is genuinely doc-irrelevant, say so and stop again.",
        }))
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
