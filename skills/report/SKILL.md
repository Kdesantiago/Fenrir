---
name: report
description: Use when you want a SESSION report — what happened THIS working session: files changed, decisions/ADRs, tests run + result, real tokens/USD from dashboard telemetry, board items touched. Triggers — "session report", "what did we do this session", "recap this session's changes + cost". NOT for repo GATE/governance state (/fenrir:status), NOT for per-User-Story cost attribution (us-cost-tracking — report consumes its numbers), NOT for formatting existing docs (doc-generator). Read-only digest; degrades to git-only with a "cost unavailable" note.
---

# Report — the session digest

A read-only recap of **what happened in THIS working session**: files changed, decisions/ADRs written, tests run and their real result, real tokens/USD from dashboard telemetry, and board items touched. It **reports, it does not enforce or mutate** — it writes nothing to gate-exceptions or branch-protection, and the dollars it shows are a DERIVED estimate from the price book, not billed cost. It is scoped to one session in one repo; cross-session or fleet roll-ups are out of scope.

## When to use
- "session report", "what did we do this session", "recap this session's changes + cost", "summarize the work + spend"
- End of a work session / before standup: a single digest of files, decisions, tests, cost, board moves
- A wrap-up step after `/fenrir:deliver` to record what the run actually did

## When NOT to use
- Repo gate/governance state (is branch-protection armed, open exceptions, onboarding) → `/fenrir:status` (it owns the gate view; this skill is session activity)
- Per-User-Story cost attribution / cost trace by US → `us-cost-tracking` (report CONSUMES its telemetry session-scoped; it does not re-attribute)
- Aggregating/formatting README/API reference/changelog from git history → `doc-generator`
- Cross-session or multi-repo/fleet reporting → out of scope (one session, one repo)

## Inputs
- The current Claude Code session id + its transcript under `~/.claude` — the source of files touched, tools/tests run, and tokens/cost.
- The companion `dashboard/` app for REAL cost: `python -m backend.cli trace` (run from `dashboard/`), `GET /api/trace`, `GET /api/telemetry/subagents`, `GET /api/telemetry/summary` — consumed, never recomputed.
- `git` — working diff + this session's commits for files changed, and any new `docs/adr/` / `docs/specs/` artifacts.
- The board store `data/boards/<project-slug>.json` (via the CLI) for items created/moved this session.
- No `org-profile.yaml` keys required.

## Steps
1. **Resolve scope.** Identify the current Claude Code session id and the repo/project slug. If the `dashboard/` app is absent or unreachable, DEGRADE to git-only (Changed / Decisions / Tests / Board) and state "Cost: unavailable (dashboard not present)" — never fabricate spend.
2. **Changed.** From `git` list files changed this session (`git diff --stat` for the working tree + `git log` for session commits): one line per path → what changed. Note any new `docs/adr/NNNN-*.md` / `docs/specs/*` written this session — these are the Decisions section's source.
3. **Decisions.** List ADRs/specs/design docs produced this session (path + the decision in one line). Do not invent rationale — link to the artifact; the `architect` agent owns the decision content.
4. **Tests.** Report which test/gate commands actually ran this session and their real result (from the transcript or `delivery-gates` output) — pass/fail, coverage if printed. Do NOT fabricate a green run; if no tests ran, say so.
5. **Cost.** Pull REAL session tokens + USD and the subagent breakdown from telemetry — `python -m backend.cli trace` (filter with `--us <id>` when the work maps to a story), `GET /api/trace`, `GET /api/telemetry/subagents`. Label USD as a **DERIVED estimate** (price book in `dashboard/backend/pricing.py`), not billed dollars. Numbers come from telemetry only — never estimated from memory.
6. **Board.** List board items created/moved/touched this session from `data/boards/<project-slug>.json` (via the CLI). The board stores only CURRENT status — there is no status-transition history — so "items moved" is INFERRED from this session's actions and must be stated as such, never presented as a recorded timeline.
7. **Emit one markdown SESSION REPORT** with sections in order: **Changed | Decisions | Tests | Cost | Board**. Close by stating it is a read-only digest — not the gate/governance view (`/fenrir:status`) and not a per-US ledger (`us-cost-tracking`), whose numbers it merely consumes.

## Output / validation
- One markdown SESSION REPORT (Changed / Decisions / Tests / Cost / Board), session-scoped.
- Validate: every cost figure reconciles with `cli trace` / `/api/trace` for the session (USD labeled DERIVED); files/tests/decisions are the session's actual git + transcript record; board moves are honestly tagged as inferred-from-actions.
- This skill REPORTS; it changes nothing. The real gate/governance state is `/fenrir:status`; the only hard gates are couche-0 (PreToolUse hooks + CI required-checks).

## Refuses when
- Asked to fabricate tokens/cost instead of reading real dashboard telemetry/trace.
- Asked to present the report as the gate/governance view or as a merge gate (defer to `/fenrir:status`; this is a read-only digest that blocks nothing).
- Asked to re-attribute per-US cost or build a costed board (defer to `us-cost-tracking`; report only consumes its numbers).
- Asked to mutate gate-exceptions / branch-protection / the board's governance state (read-only).
- Asked to aggregate across multiple sessions or repos (out of scope).
