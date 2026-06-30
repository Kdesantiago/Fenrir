# Feature — Cross-platform tracking + auto-registered hooks

> Plan target: the **fenrir plugin repo** (`Fenrir-main`). Ports the fixes proven in a
> consuming repo (DocumentIngestor) back upstream so they ship for everyone.
> ADR: [docs/adr/0003-cross-platform-tracking-and-auto-registered-hooks.md](../adr/0003-cross-platform-tracking-and-auto-registered-hooks.md)
> Board/branch: **degraded** — this download is not a git repo and has no live board, so the
> breakdown lives here. On delivery: `git init` (or clone) + branch `feat/cross-platform-tracking-auto-hooks`.

## Capability

The fenrir tracking stack works out-of-the-box on every OS, and the tracking hooks register
themselves when the plugin is enabled — no `repo-bootstrap`, no hand-edited `settings.json`.
Enforcement/guard hooks stay opt-in via `repo-bootstrap` (unchanged).

## Affected paths

- `dashboard/backend/telemetry.py` — `encode_project`, `load_events`, `_run_tokens`, meta read
- `scripts/track_session.py` — `_dash_python`
- `dashboard/backend/board.py` — load / save / `write_epic_retro`
- `hooks/hooks.json` — **new** (plugin-level auto-registration)
- `templates/.claude/settings.json` — remove the 6 tracking-hook entries (keep enforcement)
- `dashboard/tests/test_scope_cli.py`, `test_telemetry.py` — cross-platform coverage
- (US5) `dashboard/backend/config.py` + `.env` — optional date-floor

## User Stories (atomic, build order)

### US1 — Cross-platform `encode_project`
- **As a** Windows user of the dashboard
- **I want** the project slug to match `~/.claude/projects/<slug>` on Windows (lowercase drive, `\`/`:` → `-`)
- **So that** telemetry auto-scopes to my repo instead of silently matching nothing
- **AC**: `encode_project` lowercases the drive + replaces `\` `:` `/` `.`; POSIX output byte-identical to today; a Windows-path test (constructed os-independently) asserts `c--Users-...` and the existing POSIX test still passes.

### US2 — Cross-platform `_dash_python`
- **As a** tracking hook running on Windows
- **I want** `_dash_python` to find `.venv/Scripts/python.exe` as well as `.venv/bin/python`
- **So that** `backend.cli` runs under the dashboard venv (with deps) instead of a deps-less fallback → no silent no-op
- **AC**: returns the Windows venv path when present, the POSIX path when present, else `sys.executable`; unit test covers both layouts via a tmp dir.

### US3 — UTF-8 file I/O (board + telemetry)
- **As a** user with accented (FR) board titles / `→` in retros on Windows
- **I want** all board + telemetry reads/writes to use `encoding="utf-8"`
- **So that** save/load/retro don't crash with `UnicodeEncodeError` under cp1252
- **AC**: board load/save/retro + telemetry `read_text` use utf-8 (reads `errors="replace"`); a retro/round-trip test with a non-ASCII title passes (was crashing).

### US4 — Auto-register tracking hooks at plugin level
- **As a** user who just enabled the fenrir plugin
- **I want** the tracking hooks active automatically (no bootstrap, no settings edit)
- **So that** the board populates + per-US cost is non-zero from the first session
- **AC**: `hooks/hooks.json` registers tracking-open/collect/attribute/finalize + precompact-focus via exec-form (`python` + `${CLAUDE_PLUGIN_ROOT}/hooks/*.py`); the 6 tracking entries are removed from `templates/.claude/settings.json` (enforcement kept); a smoke check shows no double-fire and that a no-dashboard repo stays inert (fail-open).

### US5 — (optional) Date-floor telemetry
- **As a** user with a long history in one repo folder
- **I want** `FENRIR_DASH_SINCE` to floor telemetry to a chosen date (loaded from `dashboard/.env`)
- **So that** I can track consumption from a fresh start without deleting transcripts
- **AC**: events/runs before the floor are excluded in `load_events` + `subagent_runs`; `.env` is loaded (skipped under pytest so fixtures aren't floored); summary exposes `since`. Flag: not a compat fix — ship only if wanted upstream.

## Out of scope
- The enforcement/guard hooks (stay opt-in via `repo-bootstrap`).
- branch-protection / CI changes.
- Reworking `repo-bootstrap` beyond the template edit in US4.

## Delivery ledger (/fenrir:deliver)

Route: **full** (RISK=0; files≈7; LOC>80). ADR 0003 reused. Build: `coder` subagent (no generator fits). Validation: `qa-tester` + `red-team-destroyer`. Degraded: not a git repo → no branch/commit/ship (changes applied in place); no org-profile (meta-repo). Baseline: 8 Windows-specific test fails (retro utf-8 + POSIX-slug asserts + fixture mkdir) — the target.

| Stage | Status |
|---|---|
| architect/ADR | reused 0003 (mitigation rewritten post-redteam) |
| build US1-5 (coder) | done — 198 tests green |
| qa-tester | PASS — +12 edge tests |
| diff-redteam | FIX-FIRST → folded (CRITICAL double-fire + 2 HIGH + advisories) → re-verified |
| delivery-gates | PASS — suite exit 0, ruff clean, JSON valid |
| ship | degraded — not a git repo (no branch/commit/PR) |

## Validation (on delivery)
qa-tester: US1-3 unit tests cross-platform (Linux CI + Windows-constructed asserts); US4 a hooks.json schema/lint + double-fire smoke. red-team: encode_project edge paths (UNC, no-drive, trailing sep), `_dash_python` symlink/missing, hook exec-form quoting on paths with spaces, fail-open when no dashboard.
