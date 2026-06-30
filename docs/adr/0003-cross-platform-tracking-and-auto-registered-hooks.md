# ADR 0003 — Cross-platform tracking + plugin-level auto-registered hooks

- Status: Accepted
- Date: 2026-06-29

## Context

Field use on Windows surfaced two classes of defect that made automatic delivery
tracking silently not work, plus a setup-friction problem:

1. **The dashboard/tracking engine is POSIX-only in three spots.**
   - `dashboard/backend/telemetry.py::encode_project` builds the `~/.claude/projects/<slug>`
     key by replacing only `/` and `.`. On Windows the project dir is encoded as
     `c--Users-me-repo` (drive colon + backslashes → `-`, **drive letter lowercased**).
     The current code leaves `C:\Users\me\repo` intact → the slug never matches →
     telemetry can't scope to the repo and the board never auto-detects the project.
   - `scripts/track_session.py::_dash_python` looks only for `dashboard/.venv/bin/python`
     (Linux/macOS). On Windows the venv interpreter is `.venv/Scripts/python.exe`, so it
     falls back to `sys.executable` — often a deps-less interpreter → `backend.cli` import
     fails → every tracking command is a silent fail-open no-op.
   - `board.py` (board load/save + retro) and `telemetry.py` (transcript reads) call
     `read_text`/`write_text` with no `encoding`. On Windows the default is cp1252, which
     raises `UnicodeEncodeError` on accented (FR) board titles and the `→` char in retros.

2. **The tracking hooks are not automatic.** `.claude-plugin/plugin.json` declares no
   `hooks`; nothing registers `tracking-*`. Tracking only runs if a repo went through
   `repo-bootstrap`, which copies `hooks/*.py` into `.claude/hooks/` and merges
   `templates/.claude/settings.json`. A user who just enables the plugin gets no tracking —
   the board stays empty and per-US cost reads $0, with no signal why.

## Decision

### A. Make the engine cross-platform (behavior-preserving on POSIX)

- `encode_project`: lowercase the drive letter and also replace `\` and `:`, so
  `C:\Users\me\repo → c--Users-me-repo`. On a **POSIX host** there is no drive/backslash/colon,
  so the output is byte-identical to today → existing Linux CI stays green. The drive is
  lowercased to a *canonical* form; `current_project_slug` matches **case-insensitively** and
  returns the real dir name, so a machine that holds both `C--…` and `c--…` project dirs still
  resolves the repo instead of reading `$0`.
- `_dash_python`: probe both `.venv/bin/python` (POSIX) and `.venv/Scripts/python.exe`
  (Windows) before falling back to `sys.executable`.
- Add `encoding="utf-8"` (read: `errors="replace"`) to every board/telemetry file I/O.

### B. Auto-register the *tracking* hooks at the plugin level

Add `hooks/hooks.json` at the plugin root (auto-discovered; merges with a consuming repo's
`.claude/settings.json` — it does not replace it). Use the **exec-form** so it is
cross-platform with no shell quoting:

```json
{ "type": "command", "command": "python",
  "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/tracking-finalize.py"] }
```

`${CLAUDE_PLUGIN_ROOT}` is substituted inside `args`; `python` resolves on Windows
(launcher), macOS, and Linux. The hook scripts are pure stdlib; they locate the dashboard
and its venv through the now-cross-platform `_dash_python`, so the chain works when launched
by a plain `python` — no per-repo venv path needed in settings.

### C. Scope: auto-register ONLY the fail-open tracking hooks

Auto-register: `tracking-open` (UserPromptSubmit), `tracking-collect` (SubagentStop),
`tracking-attribute` (PostToolUse Bash — per-commit per-US), `tracking-finalize`
(Stop + SessionEnd), `precompact-focus` (PreCompact). All are fail-open by contract
(no dashboard → skip, exit 0), so they are safe on **every** repo that enables the plugin.

Scope of the promise: auto-tracking only *acts* where a dashboard companion app is present —
`<repo>/dashboard` (a `backend/` under it) or an explicit `FENRIR_DASH_DIR`. Everywhere else
the hooks fire but fail-open to a no-op. So "enable the plugin → the board populates" holds for
dashboard-bearing repos; on a plain repo the hooks are inert by design, not broken.

Do **not** auto-register the enforcement/guard hooks (`delivery-guard`, `prompt-guard`,
`content-scanner`, `config-audit`, `branch-plan-check`, `tracking-guard` commit-gate,
`iac-watch`, `tool-failure-triage`). Those can block, need `.claude/hooks/` copies and
branch-protection, and are intentionally opt-in via `repo-bootstrap`.

### D. Avoid double-fire

Because the tracking hooks now auto-register plugin-side, remove their 6 entries from
`templates/.claude/settings.json` (merged hooks both fire otherwise). The enforcement hooks
stay in that template — `repo-bootstrap` remains the opt-in path for couche-0 enforcement. The
`repo-bootstrap` SKILL is also updated to stop copying the tracking `*.py` and stop merging their
template entries.

That handles NEW bootstraps. A repo bootstrapped BEFORE this change still carries the 5 tracking
entries in its own `.claude/settings.json`, so plugin + repo both fire. `repo-bootstrap` is
**append-only and cannot self-clean** an existing repo, so we ship a one-shot
`scripts/migrate-tracking-hooks.py` (pure stdlib, idempotent, fail-safe) that strips every hook
entry referencing `{tracking-open, tracking-collect, tracking-attribute, tracking-finalize,
precompact-focus}.py`, drops any event array left empty, preserves all other hooks/keys, and
exits 0 when there is nothing to do.

## Consequences

- Enable the plugin → tracking works on Windows/macOS/Linux with zero manual settings
  editing; no dashboard → silently inert (fail-open), as designed.
- POSIX output of `encode_project` is unchanged, so existing tests pass; new tests must add
  Windows-slug coverage (constructed os-independently, not POSIX-literal asserts).
- One behavior change for existing bootstrapped repos: tracking hooks move from their
  `.claude/settings.json` (template) to plugin-level. The template + SKILL change prevents NEW
  double-wiring; existing repos must run `scripts/migrate-tracking-hooks.py` once to strip the
  stale entries (re-running `repo-bootstrap` does NOT fix it — bootstrap only appends).
- `repo-bootstrap` no longer copies the tracking `*.py` (they run from the plugin); it still
  copies the enforcement hooks (including `tracking-guard`, which is enforcement, not tracking).
