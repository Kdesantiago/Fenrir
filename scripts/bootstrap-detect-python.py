#!/usr/bin/env python3
"""Detect a working Python >=3.9 interpreter and print its ABSOLUTE path.

Per ADR 0004 (cross-OS Python hook launcher): `repo-bootstrap` bakes an absolute
interpreter path into the consuming repo's `.claude/settings.json` enforcement hooks,
because no single bare token (`python` / `python3` / `py`) is a real executable on all
three OSes. This script is the detection mechanism.

Resolution order (first that qualifies wins):
    1. sys.executable  — the interpreter already running this script is known-good and
       has the right version; no subprocess needed.
    2. py -3           — the Windows python.org launcher.
    3. python3         — POSIX convention (PEP 394).
    4. python          — last resort.

A candidate qualifies when it is Python >=3.9. The first qualifying candidate's
*absolute* interpreter path is printed to stdout and the script exits 0.

If NONE qualifies, a clear message is printed to stderr and the script exits 1 — so
`repo-bootstrap` refuses rather than bake a gate that will crash.

Pure stdlib. Cross-platform (no bash-isms; uses shutil.which + subprocess).

Usage:  python scripts/bootstrap-detect-python.py
        (prints e.g. /usr/bin/python3 and exits 0)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

MIN_VERSION = (3, 9)

# Probe that prints the interpreter's own absolute path IFF it satisfies the floor.
# Run inside each candidate so we trust the candidate's *own* sys.version / sys.executable,
# never a parse of `--version` text (which varies and can lie about which binary ran).
_PROBE = (
    "import sys,os;"
    "ver=sys.version_info;"
    "exe=sys.executable or '';"
    f"sys.exit(0) if ver[:2] >= ({MIN_VERSION[0]},{MIN_VERSION[1]}) and exe else sys.exit(3);"
)

# A second probe to emit the absolute path on its own line (kept separate so the exit-code
# probe above stays a pure pass/fail). Prints abspath of sys.executable.
_PATH_PROBE = "import sys,os;print(os.path.abspath(sys.executable))"


def _version_ok(version_info: tuple[int, int]) -> bool:
    return tuple(version_info) >= MIN_VERSION


def _candidate_commands() -> list[list[str]]:
    """Argv prefixes to try, in resolution order. Each is the command that launches the
    candidate interpreter; the probe script is appended via `-c`."""
    cands: list[list[str]] = []
    # 1. The running interpreter — no subprocess required, handled specially by the caller.
    #    Represented here as a sentinel empty-meaning entry is avoided; we check it directly.
    # 2. Windows launcher.
    if shutil.which("py"):
        cands.append(["py", "-3"])
    # 3 + 4. POSIX tokens.
    for tok in ("python3", "python"):
        if shutil.which(tok):
            cands.append([tok])
    return cands


def _probe(argv_prefix: list[str]) -> str | None:
    """Run the floor check + path probe under `argv_prefix`. Returns the absolute interpreter
    path on success, else None. Never raises."""
    try:
        # Floor gate first (exit 0 == ok).
        gate = subprocess.run(
            [*argv_prefix, "-c", _PROBE],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if gate.returncode != 0:
            return None
        # Now fetch the absolute path of that same interpreter.
        out = subprocess.run(
            [*argv_prefix, "-c", _PATH_PROBE],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return None
        path = out.stdout.strip().splitlines()[-1].strip() if out.stdout.strip() else ""
        return path or None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def detect() -> str | None:
    """Return the absolute path of the first qualifying interpreter, or None."""
    # 1. sys.executable — the interpreter running us. Known-good if it meets the floor.
    if _version_ok(sys.version_info[:2]) and sys.executable:
        return os.path.abspath(sys.executable)
    # 2..4. Probe external candidates.
    for argv_prefix in _candidate_commands():
        path = _probe(argv_prefix)
        if path:
            return path
    return None


def main() -> int:
    path = detect()
    if path:
        print(path)
        return 0
    floor = f"{MIN_VERSION[0]}.{MIN_VERSION[1]}"
    sys.stderr.write(
        f"bootstrap-detect-python: no working Python >={floor} interpreter found.\n"
        f"Install Python >={floor} (https://www.python.org/downloads/) and re-run.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
