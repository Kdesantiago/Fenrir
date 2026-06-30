#!/usr/bin/env python3
"""Strip the now-plugin-level tracking hooks from a repo's `.claude/settings.json`.

The delivery-tracking hooks (`tracking-open`, `tracking-collect`, `tracking-attribute`,
`tracking-finalize`, `precompact-focus`) auto-register at the PLUGIN level (`hooks/hooks.json`)
and run from there on every OS. A repo bootstrapped BEFORE that change still carries those
entries in its `.claude/settings.json`; since both fire, every tracked event runs twice.

`repo-bootstrap` is append-only and cannot self-clean, so this one-shot migration removes the
stale entries. It is pure stdlib, idempotent (a second run is a no-op), and fail-safe: a missing
file / nothing-to-do exits 0 without writing. The enforcement hooks (including `tracking-guard`,
which is enforcement, not tracking) are preserved untouched.

Usage:  python scripts/migrate-tracking-hooks.py [REPO_ROOT]
        (REPO_ROOT defaults to $CLAUDE_PROJECT_DIR, then the current directory)
Prints a JSON summary of what was removed.
"""
from __future__ import annotations

import json
import os
import sys

# The scripts whose hook entries move to the plugin level. `tracking-guard` is deliberately
# NOT here: it is an enforcement (commit-gate) hook and stays in `.claude/settings.json`.
_TRACKING_SCRIPTS = (
    "tracking-open.py",
    "tracking-collect.py",
    "tracking-attribute.py",
    "tracking-finalize.py",
    "precompact-focus.py",
)


def _repo_root(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1].strip():
        return argv[1]
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _references_tracking(hook: dict) -> bool:
    """True if a single hook object invokes one of the plugin-level tracking scripts, whether it
    uses the shell-string `command` form or the exec-form `command` + `args` list."""
    if not isinstance(hook, dict):
        return False
    parts: list[str] = []
    cmd = hook.get("command")
    if isinstance(cmd, str):
        parts.append(cmd)
    args = hook.get("args")
    if isinstance(args, list):
        parts.extend(str(a) for a in args)
    blob = " ".join(parts)
    return any(script in blob for script in _TRACKING_SCRIPTS)


def migrate(settings_path: str) -> dict:
    """Remove stale tracking entries from `settings_path`. Returns a summary dict; writes the file
    only when something actually changed."""
    summary: dict = {"path": settings_path, "changed": False, "removed": [], "emptied_events": []}
    if not os.path.isfile(settings_path):
        summary["reason"] = "no settings.json"
        return summary
    try:
        with open(settings_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        summary["reason"] = f"unreadable/invalid JSON: {e}"
        return summary
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        summary["reason"] = "no hooks block"
        return summary

    removed: list[str] = []
    emptied: list[str] = []
    for event in list(hooks.keys()):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        new_groups: list = []
        for group in groups:
            if not isinstance(group, dict):
                new_groups.append(group)
                continue
            inner = group.get("hooks")
            if not isinstance(inner, list):
                new_groups.append(group)
                continue
            kept = []
            for hook in inner:
                if _references_tracking(hook):
                    removed.append(event)
                else:
                    kept.append(hook)
            if kept:
                group["hooks"] = kept
                new_groups.append(group)
            # group whose hooks all referenced tracking -> drop the whole group
        if new_groups:
            hooks[event] = new_groups
        else:
            # event array left empty -> drop the event key entirely
            del hooks[event]
            emptied.append(event)

    if not removed and not emptied:
        summary["reason"] = "nothing to do (no tracking entries)"
        return summary

    tmp = settings_path + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, settings_path)
    summary.update({"changed": True, "removed": removed, "emptied_events": emptied})
    return summary


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    root = _repo_root(argv)
    settings_path = os.path.join(root, ".claude", "settings.json")
    summary = migrate(settings_path)
    print(json.dumps(summary, indent=2))
    return 0  # fail-safe: always exit 0


if __name__ == "__main__":
    sys.exit(main())
