# ADR 0004 — Cross-OS Python hook launcher (one canonical invocation per layer)

- Status: Accepted
- Date: 2026-06-29

## Context

The plugin has **two** layers of Python hooks, wired two different ways, and **neither
invocation resolves on every OS**. The result is silent: a hook that does not spawn produces
no error — it just never runs.

### 1. Plugin-level tracking hooks — exec-form `python`, absent on this host

`hooks/hooks.json` auto-registers the 6 fail-open tracking hooks in **exec form**:

```json
{ "type": "command", "command": "python",
  "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/tracking-open.py"] }
```

The header comment asserts "`python` resolves on Windows (launcher), macOS, and Linux." That is
**wrong on two of the three**:

- **This macOS host has no `python`** — `command -v python` → absent; only `/usr/bin/python3`
  exists (Python 3.9.6). So the tracking hooks never spawn here. Modern macOS and most Linux
  distros ship `python3`, not `python` (PEP 394).
- **Default Windows has no real `python` either.** A python.org install puts the real
  interpreter under `…\AppData\Local\Programs\Python\…` and, by default, **the launcher
  `py.exe` is the only thing reliably on `PATH`** (installed for all users into `C:\Windows`);
  python.org's installer "by default will not change your system path" for `python.exe`. The
  bare `python`/`python3` that appear on a clean Windows `PATH` are **Microsoft Store App
  Execution Alias stubs** that error out when given arguments. So exec-form `python <script>`
  fails on a default Windows+python.org machine too.

Authoritative semantics (Claude Code hooks reference): in **exec form there is no shell** —
"Claude Code resolves `command` as an executable on `PATH` and spawns it directly … On
Windows, exec form requires `command` to resolve to a real executable such as a `.exe`."
No shebang is honored, no `.py` association is used, no shell builtin or `PATHEXT` magic for a
bare interpreter name beyond locating a real binary. `${CLAUDE_PLUGIN_ROOT}` **is** substituted
into both `command` and every `args` element in both forms — that part works; the failure is
purely the interpreter token.

### 2. Repo-level enforcement hooks — shell-string `python3 "$CLAUDE_PROJECT_DIR/…"`, breaks on Windows

`templates/.claude/settings.json` (installed by `repo-bootstrap`) registers **11 enforcement
hooks** in **shell-string form**:

```json
{ "type": "command",
  "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/delivery-guard.py\"" }
```

Shell form runs under `sh -c` on macOS/Linux and **Git Bash on Windows, or PowerShell when Git
Bash isn't installed**. Consequences:

- On **macOS/Linux** `python3` resolves and `$CLAUDE_PROJECT_DIR` expands — fine **today**, but
  brittle: it assumes the bare token `python3`.
- On **Windows without Git Bash** the string is handed to **PowerShell**, where neither
  `python3` nor POSIX `$CLAUDE_PROJECT_DIR` syntax resolves (`$CLAUDE_PROJECT_DIR` is a
  PowerShell variable, not the exported env var `%CLAUDE_PROJECT_DIR%`). The **entire
  deterministic enforcement gate silently no-ops on Windows.**

### 3. `from datetime import UTC` crashes the gate on Python 3.9 / 3.10

Independently of the launcher, **6 enforcement hooks** import `UTC` from `datetime`
(`prompt-guard`, `session-end`, `tool-failure-triage`, `config-audit`, `content-scanner`,
`delivery-guard`):

```python
from datetime import UTC, datetime   # UTC added in 3.11
… datetime.now(UTC).isoformat()
```

`datetime.UTC` is **3.11+**. This very host is **3.9.6** — so even once the launcher finds an
interpreter, all 6 crash at import. A hook that raises on import is treated as a failed hook;
for the PreToolUse guards that is a fail-*open* path on a non-zero spawn, i.e. the gate is gone.

### Net

No single interpreter token (`python` / `python3` / `py`) is present as a real executable on
all three OSes: `python3` ≈ POSIX-only, `py` ≈ Windows-only, `python` ≈ neither by default.
So a single static exec-form token **cannot** be correct everywhere. The fix must be
**per-layer**, because the two layers have different freedoms.

## Decision

Use **different mechanisms per layer** — the static plugin layer gets the most-portable static
launcher; the repo layer gets a per-machine baked interpreter. Plus a 3.9 floor fix.

### A. Repo-level enforcement hooks → bootstrap-time interpreter DETECTION baked as exec-form

The enforcement hooks are written **per machine** by `repo-bootstrap`, so they can be
deterministic: detect the interpreter once at bootstrap and bake it. Add a tiny
`scripts/bootstrap-detect-python.py` step (run by `repo-bootstrap`) that resolves the **first
working interpreter** in order — `sys.executable` (the interpreter already running bootstrap is
known-good and has the right version), then `py -3`, `python3`, `python` — verifies it is
**≥ 3.9** and can import stdlib, then writes each enforcement hook entry into the repo's
`.claude/settings.json` in **exec form**:

```json
{ "type": "command",
  "command": "<DETECTED_INTERPRETER>",
  "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/delivery-guard.py"] }
```

where `<DETECTED_INTERPRETER>` is the **absolute path** to the resolved interpreter (e.g.
`/usr/bin/python3` on this host, `C:\\Users\\me\\AppData\\Local\\Programs\\Python\\Python312\\python.exe`
on Windows). Exec form means **no shell, no Git Bash/PowerShell dependency, no `$VAR`
expansion** — `${CLAUDE_PROJECT_DIR}` is substituted by Claude Code itself into the `args`
element on every OS, and the absolute interpreter path is spawned directly. This is the most
robust option for this layer: it removes both the `python3`-token assumption and the
shell-portability assumption in one move, and it is verifiable at bootstrap (we know it ran).

`templates/.claude/settings.json` is converted from shell-string to **exec-form templates** with
a `"${PYTHON}"` placeholder so the file stays valid/reviewable; `repo-bootstrap` replaces
`${PYTHON}` with the detected absolute path when it merges into the repo. (If a machine somehow
has only a `<3.9` interpreter, bootstrap **refuses with a clear message** rather than baking a
gate that will crash.)

### B. Plugin-level static `hooks.json` → most-portable static exec-form: `py`-aware shim is NOT exec'able, so use a committed launcher invoked in **shell form**

This file is static and shipped with the plugin — it **cannot** be per-machine baked. We
evaluated the three candidates concretely:

- **(a) Committed launcher shim resolved via `${CLAUDE_PLUGIN_ROOT}`, exec'd directly.**
  Rejected. In exec form `command` must be a **real executable**; a `launcher.py`/`launcher.sh`
  is not spawnable by name on Windows (no shebang honored, `.py`/`.sh` are not executables),
  so `"command": "${CLAUDE_PLUGIN_ROOT}/launcher"` fails on Windows. Exec-ing a shim does not
  remove the chicken-and-egg — you still need a real interpreter/shell to run the shim.

- **(c-static) A single bare interpreter token in exec form** (`python` / `python3` / `py`).
  Rejected: as established, none is present on all three OSes by default.

- **(b-static, CHOSEN) A committed POSIX-shell launcher invoked in SHELL form.** Ship
  `hooks/run-python.sh` (committed, executable) that probes, in order, `python3` → `python` →
  `py -3` and `exec`s the **first one that exists**, passing the script path through. Register
  it in `hooks.json` in **shell form** (no `args`), quoting the placeholder:

  ```json
  { "type": "command",
    "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-python.sh\" \"${CLAUDE_PLUGIN_ROOT}/hooks/tracking-open.py\"" }
  ```

  Shell form runs under `sh -c` on macOS/Linux (the shim runs, probes `python3`, works **here**)
  and under **Git Bash on Windows** (the same POSIX shim runs, probes `py -3`, works) — Git Bash
  is bundled with Git for Windows, which is a near-universal prerequisite for using Claude Code
  with git on Windows. **Residual risk:** a Windows user with **no Git Bash** gets PowerShell
  for shell form, where the `.sh` shim will not run. For that case the launcher script's first
  line documents the one-time fix (install Git for Windows, or run `repo-bootstrap` which bakes
  the absolute interpreter for the layer that can be baked). Tracking is **fail-open by
  contract** (no spawn → no tracking, never a block), so this degradation loses telemetry, never
  safety.

  This is strictly more portable than today's `"command": "python"` (which is broken on macOS
  **and** default Windows), and it keeps the plugin layer static as required.

**Both layers stated explicitly:** repo-level enforcement = **(A) per-machine baked absolute
interpreter, exec form**; plugin-level tracking = **(B) committed `run-python.sh`, shell form**.

### C. Python floor = 3.9; replace `datetime.UTC` with `datetime.now(timezone.utc)`

Set the documented floor at **`>=3.9`** (matches this host's 3.9.6 and the project's existing
3.9-era `from __future__ import annotations` usage). Fix all 6 hooks:

```python
from datetime import datetime, timezone
… datetime.now(timezone.utc).isoformat()   # identical output, works 3.9+
```

`timezone.utc` is available since 3.2 and `datetime.now(timezone.utc).isoformat()` is
byte-identical to `datetime.now(UTC).isoformat()`. Document `requires-python = ">=3.9"` for the
hook layer and have `bootstrap-detect-python.py` **enforce** it.

## Consequences

- Enabling the plugin makes the **tracking** hooks actually spawn on macOS/Linux (via `sh -c` +
  `python3`) and on Windows-with-Git-Bash (via Git Bash + `py -3`) — closing the silent gap on
  this host. Windows-without-Git-Bash degrades to no-tracking (fail-open), with a documented fix.
- `repo-bootstrap` now makes the **enforcement** gate fire on Windows for the first time: exec
  form + absolute interpreter removes the PowerShell/`python3`/`$VAR` failure mode entirely.
- The gate no longer crashes on Python 3.9/3.10; the floor is explicit and enforced at bootstrap.
- New surface to maintain: one committed shell shim (`hooks/run-python.sh`) and one bootstrap
  detector (`scripts/bootstrap-detect-python.py`). `templates/.claude/settings.json` changes
  shape (shell-string → exec-form-with-`${PYTHON}`); existing bootstrapped repos keep their old
  shell-string entries until re-bootstrapped (still works on POSIX; a follow-up migration like
  `migrate-tracking-hooks.py` can rewrite them to exec form).
- ADR 0003's header-comment claim ("`python` resolves on Windows/macOS/Linux") is superseded by
  this ADR; `hooks/hooks.json`'s comment must be corrected to describe the shim.

## Exact artifacts the build phase must produce

### 1. `hooks/run-python.sh` (committed, `chmod +x`)

```sh
#!/usr/bin/env bash
# Cross-OS Python launcher for plugin-level (static) hooks. Invoked in SHELL form from
# hooks.json so it runs under sh -c (macOS/Linux) or Git Bash (Windows). Probes a real
# interpreter and exec's it. Fail-open: if none found, exit 0 (tracking is best-effort).
# Requires Python >=3.9 (the hooks use from __future__ import annotations + timezone.utc).
set -u
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then exec "$cand" "$@"; fi
done
if command -v py >/dev/null 2>&1; then exec py -3 "$@"; fi   # Windows python.org launcher
exit 0
```

### 2. `hooks/hooks.json` — each entry in SHELL form (example, one of the six)

```json
{
  "type": "command",
  "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-python.sh\" \"${CLAUDE_PLUGIN_ROOT}/hooks/tracking-open.py\""
}
```

(Apply the same shape to `tracking-collect.py`, `tracking-attribute.py`,
`tracking-finalize.py` ×2 events, `precompact-focus.py`. Update the file's `//` comment to
describe the shim + the no-Git-Bash caveat.)

### 3. Per-machine `.claude/settings.json` enforcement entry shape (what bootstrap bakes)

Template form shipped in `templates/.claude/settings.json`:

```json
{
  "type": "command",
  "command": "${PYTHON}",
  "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/delivery-guard.py"]
}
```

Baked form written into the repo by `repo-bootstrap` (macOS example):

```json
{
  "type": "command",
  "command": "/usr/bin/python3",
  "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/delivery-guard.py"]
}
```

(`${PYTHON}` → absolute path of the detected ≥3.9 interpreter; `${CLAUDE_PROJECT_DIR}` left
verbatim — Claude Code substitutes it at runtime. Same shape for all 11 enforcement hooks.)

### 4. `scripts/bootstrap-detect-python.py` (mechanism)

Pure stdlib. Resolution order: `sys.executable` → `py -3` → `python3` → `python`. For each
candidate run `-c "import sys;assert sys.version_info>=(3,9)"`; the first that passes is the
detected interpreter (emit its **absolute** path). If none qualifies, **exit non-zero with a
message** telling the user to install Python ≥3.9 — `repo-bootstrap` refuses rather than bake a
crashing gate.

### 5. The 6 `datetime.UTC` fixes

In each of `hooks/{prompt-guard,session-end,tool-failure-triage,config-audit,content-scanner,delivery-guard}.py`:
`from datetime import UTC, …` → `from datetime import …, timezone` and `datetime.now(UTC)` →
`datetime.now(timezone.utc)`.

## Cross-OS validation plan (verify phase)

**macOS/Linux — prove each plugin (tracking) hook fires (run on this host):**

```sh
# (a) shim resolves an interpreter here (must print a path, exit 0)
hooks/run-python.sh -c 'import sys;print(sys.executable)'

# (b) each tracking hook spawns via the shim with a synthetic event and exits 0
for s in tracking-open tracking-collect tracking-attribute tracking-finalize precompact-focus; do
  echo '{"session_id":"verify","cwd":"'"$PWD"'"}' \
    | hooks/run-python.sh "hooks/$s.py"; echo "$s -> exit $?"
done
```

**macOS/Linux — prove the enforcement gate runs under the baked interpreter and no longer
crashes on 3.9:**

```sh
PY=$(python3 scripts/bootstrap-detect-python.py)     # prints absolute path, exits 0
"$PY" -c 'import sys;assert sys.version_info>=(3,9);print("floor ok",sys.version)'
# every enforcement hook imports + runs clean (the UTC fix); deny path still denies
for h in delivery-guard prompt-guard content-scanner config-audit session-end \
         tool-failure-triage branch-plan-check session-context doc-staleness \
         iac-watch tracking-guard; do
  echo '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' \
    | "$PY" "hooks/$h.py" >/dev/null; echo "$h -> exit $?"   # 0 == imported & ran
done
# regression-proof the UTC fix specifically:
"$PY" -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).isoformat())'
```

All hook spawns must exit 0 (or the documented deny code for a guard given a blocked command);
**none may raise `ImportError: cannot import name 'UTC'`** — that is the 3.9 regression this ADR
closes.

**Windows — what the user must see** (manual, documented in the PR):

- With Git for Windows installed: enabling the plugin and submitting a prompt populates the
  dashboard board (tracking shim runs under Git Bash → `py -3`); the `session-context` hook's
  banner appears at session start (enforcement runs under the baked absolute `python.exe`).
- `python scripts\bootstrap-detect-python.py` prints an **absolute** `…\python.exe` path and
  exits 0; the baked `.claude\settings.json` entries show that path as `command` with the
  `.py` script as a single `args` element.
- Without Git Bash: tracking is silently absent (fail-open, by design) but the **enforcement
  gate still fires** because exec form needs no shell — confirming the two-layer split degrades
  safely.

## Sources

- [Hooks reference — Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Automate actions with hooks — Claude Code Docs](https://code.claude.com/docs/en/hooks-guide)
- [Using Python on Windows — Python 3.x docs (py launcher, PATH)](https://docs.python.org/3/using/windows.html)
