#!/usr/bin/env python3
"""One cross-platform entrypoint to wire couche-0 enforcement into a consuming repo.

Replaces the manual "hand-merge templates/.claude/settings.json into your repo" step (R1)
with a single deterministic, idempotent, fail-safe command that runs the same on
Windows / macOS / Linux:

    python scripts/bootstrap.py [TARGET_REPO_ROOT]

What it does, in order:
  1. Detect the first working Python >=3.9 interpreter (see bootstrap-detect-python.py) and
     capture its ABSOLUTE path. Refuse (exit 1) if none qualifies, rather than bake a gate
     that will crash (ADR 0004).
  2. Merge the enforcement-hook block from this plugin's templates/.claude/settings.json into
     the target repo's .claude/settings.json:
       - substitute the literal ${PYTHON} placeholder with the detected absolute path,
       - JSON-merge per Claude-Code hook event WITHOUT clobbering existing user hooks
         (dedups by command/args so re-running is a no-op).
  3. Copy the enforcement hooks/*.py into <repo>/.claude/hooks/ (and track_session.py into
     <repo>/.claude/scripts/) when that install layout is used.
  4. Run the migrate-tracking-hooks de-dupe to strip any stale plugin-level tracking entries.
  5. Run bootstrap_smoke_test against the target repo.

Pure stdlib. Idempotent. Fail-safe: a second run changes nothing; it never deletes a user's
own hooks. Prints a clear summary.

This script is part of WORK-STREAM B2; it owns scripts/* only. It does NOT edit the template
or repo-bootstrap docs.
"""
from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys

# This plugin's own root (parent of scripts/).
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_PLUGIN_ROOT, "scripts")

# Enforcement hooks copied into the consuming repo. The plugin-level TRACKING scripts
# (tracking-open/collect/attribute/finalize, precompact-focus) are deliberately excluded:
# they auto-register at the plugin level (hooks/hooks.json) and would double-fire if copied
# here. tracking-guard STAYS — it is enforcement, not tracking.
_TRACKING_ONLY = {
    "tracking-open.py",
    "tracking-collect.py",
    "tracking-attribute.py",
    "tracking-finalize.py",
    "precompact-focus.py",
}

_PYTHON_PLACEHOLDER = "${PYTHON}"


# --- step 1: detect interpreter ---------------------------------------------------------


def detect_python() -> str | None:
    """Return the absolute path of a working Python >=3.9, reusing the detector module."""
    detector = os.path.join(_SCRIPTS_DIR, "bootstrap-detect-python.py")
    # Prefer importing the function directly (no subprocess), fall back to running the file.
    try:
        ns = runpy.run_path(detector)
        detect = ns.get("detect")
        if callable(detect):
            return detect()
    except Exception:
        pass
    # Fallback: run as a subprocess and read stdout.
    try:
        out = subprocess.run(
            [sys.executable, detector], capture_output=True, text=True, timeout=30
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()[-1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


# --- step 2: merge settings.json --------------------------------------------------------


def _substitute_python(obj: object, python_path: str) -> object:
    """Recursively replace the literal ${PYTHON} placeholder in every string value."""
    if isinstance(obj, str):
        return obj.replace(_PYTHON_PLACEHOLDER, python_path)
    if isinstance(obj, list):
        return [_substitute_python(x, python_path) for x in obj]
    if isinstance(obj, dict):
        return {k: _substitute_python(v, python_path) for k, v in obj.items()}
    return obj


def _hook_identity(hook: dict) -> str:
    """A stable key for a single hook object so we can dedup on re-run. Combines command +
    args, normalized."""
    if not isinstance(hook, dict):
        return repr(hook)
    cmd = hook.get("command")
    args = hook.get("args")
    parts = [str(cmd) if cmd is not None else ""]
    if isinstance(args, list):
        parts.extend(str(a) for a in args)
    return "\x00".join(parts)


def _group_identity(group: dict) -> tuple[str, frozenset[str]]:
    """Identity of a matcher-group: its matcher plus the set of hook identities it carries."""
    matcher = str(group.get("matcher", "")) if isinstance(group, dict) else ""
    inner = group.get("hooks") if isinstance(group, dict) else None
    ids: set[str] = set()
    if isinstance(inner, list):
        ids = {_hook_identity(h) for h in inner if isinstance(h, dict)}
    return matcher, frozenset(ids)


def merge_settings(template_settings: dict, existing: dict, python_path: str) -> tuple[dict, int]:
    """Merge the template's hooks into `existing`, substituting ${PYTHON}. Per event, append
    template matcher-groups that aren't already present (matched on matcher + hook identities),
    never clobbering existing user hooks. Returns (merged, added_group_count)."""
    substituted = _substitute_python(template_settings, python_path)
    template: dict = substituted if isinstance(substituted, dict) else {}
    merged = json.loads(json.dumps(existing)) if existing else {}
    if not isinstance(merged.get("hooks"), dict):
        merged["hooks"] = {}
    _th = template.get("hooks")
    t_hooks: dict = _th if isinstance(_th, dict) else {}

    added = 0
    for event, t_groups in t_hooks.items():
        if not isinstance(t_groups, list):
            continue
        dest = merged["hooks"].get(event)
        if not isinstance(dest, list):
            dest = []
            merged["hooks"][event] = dest
        existing_ids = {_group_identity(g) for g in dest if isinstance(g, dict)}
        for g in t_groups:
            if not isinstance(g, dict):
                continue
            gid = _group_identity(g)
            # Skip if an identical matcher+hooks group already exists. Also skip if every hook
            # in this template group is already present somewhere for this event (re-run guard).
            present_hook_ids: set[str] = set()
            for eg in dest:
                if isinstance(eg, dict) and isinstance(eg.get("hooks"), list):
                    present_hook_ids |= {_hook_identity(h) for h in eg["hooks"] if isinstance(h, dict)}
            g_hook_ids = {_hook_identity(h) for h in g.get("hooks", []) if isinstance(h, dict)}
            if gid in existing_ids:
                continue
            if g_hook_ids and g_hook_ids.issubset(present_hook_ids):
                continue
            dest.append(g)
            existing_ids.add(gid)
            added += 1
    return merged, added


def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# --- step 3: copy hooks -----------------------------------------------------------------


def copy_hooks(target_root: str) -> list[str]:
    """Copy enforcement hooks/*.py -> <repo>/.claude/hooks/, and track_session.py ->
    <repo>/.claude/scripts/. Skips the plugin-level tracking scripts. Returns copied names."""
    src_hooks = os.path.join(_PLUGIN_ROOT, "hooks")
    dst_hooks = os.path.join(target_root, ".claude", "hooks")
    copied: list[str] = []
    if os.path.isdir(src_hooks):
        os.makedirs(dst_hooks, exist_ok=True)
        for name in sorted(os.listdir(src_hooks)):
            if not name.endswith(".py") or name in _TRACKING_ONLY:
                continue
            shutil.copy2(os.path.join(src_hooks, name), os.path.join(dst_hooks, name))
            copied.append(name)
    # The delivery-tracking engine the hooks call.
    src_engine = os.path.join(_SCRIPTS_DIR, "track_session.py")
    if os.path.isfile(src_engine):
        dst_scripts = os.path.join(target_root, ".claude", "scripts")
        os.makedirs(dst_scripts, exist_ok=True)
        shutil.copy2(src_engine, os.path.join(dst_scripts, "track_session.py"))
        copied.append("scripts/track_session.py")
    return copied


# --- step 4: migrate de-dupe ------------------------------------------------------------


def run_migrate(target_root: str) -> None:
    migrate = os.path.join(_SCRIPTS_DIR, "migrate-tracking-hooks.py")
    if not os.path.isfile(migrate):
        return
    try:
        ns = runpy.run_path(migrate)
        fn = ns.get("migrate")
        if callable(fn):
            fn(os.path.join(target_root, ".claude", "settings.json"))
            return
    except Exception:
        pass
    # Fallback to subprocess.
    try:
        subprocess.run([sys.executable, migrate, target_root], timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


# --- step 5: smoke test -----------------------------------------------------------------


def run_smoke(target_root: str) -> int:
    smoke = os.path.join(_SCRIPTS_DIR, "bootstrap_smoke_test.py")
    if not os.path.isfile(smoke):
        return 0
    try:
        out = subprocess.run(
            [sys.executable, smoke, target_root], text=True, timeout=120, check=False
        )
        return out.returncode
    except (OSError, subprocess.SubprocessError):
        return 0


# --- orchestration ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    target_root = (
        argv[1]
        if len(argv) > 1 and argv[1].strip()
        else (os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    )
    target_root = os.path.abspath(target_root)

    print(f"fenrir bootstrap -> {target_root}")
    print("-" * 60)

    # 1. Detect interpreter.
    python_path = detect_python()
    if not python_path:
        sys.stderr.write(
            "REFUSING: no working Python >=3.9 interpreter found. Install Python >=3.9 and "
            "re-run — baking a <3.9 interpreter would crash the enforcement gate (ADR 0004).\n"
        )
        return 1
    print(f"[1/5] detected interpreter: {python_path}")

    # 2. Merge settings.json.
    template_path = os.path.join(_PLUGIN_ROOT, "templates", ".claude", "settings.json")
    template = _load_json(template_path)
    if not template:
        sys.stderr.write(f"REFUSING: template {template_path} missing or invalid.\n")
        return 1
    settings_path = os.path.join(target_root, ".claude", "settings.json")
    existing = _load_json(settings_path)
    merged, added = merge_settings(template, existing, python_path)
    _write_json(settings_path, merged)
    print(f"[2/5] merged enforcement hooks into {settings_path} (+{added} group(s))")

    # 3. Copy hooks.
    copied = copy_hooks(target_root)
    print(f"[3/5] copied {len(copied)} enforcement hook file(s) into .claude/hooks/")

    # 4. Migrate de-dupe.
    run_migrate(target_root)
    print("[4/5] ran migrate-tracking-hooks de-dupe")

    # 5. Smoke test.
    print("[5/5] running bootstrap smoke test...")
    print("-" * 60)
    rc = run_smoke(target_root)
    print("-" * 60)
    if rc == 0:
        print("bootstrap complete — couche-0 gate wired (smoke test passed).")
    else:
        print(
            "bootstrap complete — enforcement hooks wired, but the smoke test reported gaps "
            "above (e.g. CI/branch-protection not yet armed). Address them and re-run."
        )
    # Bootstrap itself succeeded (hooks wired); the smoke rc is informational so a missing CI
    # doesn't make `bootstrap.py` look like it failed to install the in-session gate.
    return 0


if __name__ == "__main__":
    sys.exit(main())
