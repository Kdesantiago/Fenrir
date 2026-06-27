# Spec v2 — Per-US cost, cost trace & subagent attribution (honest slice)

- Status: Accepted (v2 — redesigned to the red-team's recommended slice after VERDICT: REDESIGN on v1)
- Date: 2026-06-27
- Slug: us-cost-accounting

## What v1 got killed for (and how v2 fixes it)
- **Double-counting** subagent tokens (telemetry sidechain events + `toolUseResult.usage`)
  → v2: tokens have ONE source (sidechain telemetry events). `toolUseResult`/`*.meta.json`
  are used ONLY for identity (agent_type, when, duration, model, status). Subagent token
  totals are a **partition of the existing `by_source: subagent` total**, with an explicit
  `unattributed` remainder — never added on top.
- **Unwired trace writer / "automate"** → v2: attribution is an explicit, manual
  `cli link --session <id>` (or `cli attribute`), documented. No claim of mid-run auto-write.
- **Dead consumer hooks + "force"** → v2: **no new plugin hook is shipped to consumer repos**
  and the word "force" is dropped. The formalism is a SKILL (advisory methodology) + a
  README walkthrough. Honest framing: *encourage + record*, not *force*.
- **Workflow subagents missed** → v2: subagent identity is read from BOTH inline
  `toolUseResult` AND `subagents/**/*.meta.json`; tokens from the sidechain event stream
  `find_transcripts` already scans. Unmatched runs are reported, not dropped.
- **No "coder" agent / main-thread coder** → v2: main-thread spend is captured by
  `cli link --session` (not `toolUseResult`); we do not reference a non-existent `coder.md`.
- **work_log vs trace drift** → v2: the board `work_log` is the SINGLE source; the "trace"
  is a DERIVED read (flatten work_log chronologically). No second store, no drift.
- **link double-write / no breakdown** → v2: `link` writes one entry per (source/agent)
  group AND is idempotent per `(session_id, us_id)` (skips if already linked). WorkLogEntry
  gains `source` + `subagent_type`.
- **`[1m]` tier pricing** → v2: pricing strips the `[..]` tier suffix to match the family
  and notes the long-context premium is not modeled.

## Scope (read-only views over real telemetry + the board + manual link)

### A. Per-US cost (+ per-agent breakdown)
- `board.costs()` → per Epic/Feature/US: `{input_tokens, output_tokens, cost_usd,
  by_agent:[{agent, input_tokens, output_tokens, cost_usd, entries}]}` summed from
  `work_log`; US rolls up into its Feature and Epic. API `GET /api/board/costs`.
- SPA: per-agent cost breakdown in the story modal; cost rollup badge on Feature/Epic.

### B+E. Cost trace (derived, single source) + saved US traces
- `GET /api/trace?us=<id>` and `cli trace [--us <id>]` flatten every `work_log` entry
  (across all US, or one US) into a chronological, readable cost trace
  `{at, us_id, title, agent, subagent_type, session_id, input_tokens, output_tokens,
  cost_usd, source, note}`. The board JSON (git-tracked) is the persisted trace — no second
  file to drift.

### C. Subagent attribution (who/what/when/how-much)
- `telemetry.subagent_runs(claude_dir, project)`:
  - **Identity** from inline `toolUseResult` records (`agentType, prompt→description,
    timestamp, resolvedModel, status, totalDurationMs`) and `subagents/**/*.meta.json`
    (`agentType, description, toolUseId`).
  - **Tokens/cost** from the sidechain (`isSidechain`/subagent-file) events already loaded —
    matched to a run by `agentId`/`toolUseId`/session where possible.
  - Returns `{runs:[{agent_type, description, when, model, status, duration_ms,
    input_tokens, output_tokens, cost_usd, attributed:bool}], by_type:[…],
    subagent_total_tokens, attributed_tokens, unattributed_tokens}` — a reconciled
    partition (attributed + unattributed == the subagent total from `by_source`).
- API `GET /api/telemetry/subagents?project=`; SPA: a **Subagents** panel under Agents
  (runs table: type · when · model · in/out tokens · cost · duration · status; by-type bar;
  an "unattributed" note).

### D. Formalism (advisory — encourage + record, NOT force)
- New skill **`us-cost-tracking`** (`skills/us-cost-tracking/SKILL.md` + `VERIFY.md`): the
  working contract — represent substantive work as a US on the board, then after a stage run
  `cli link --session <id>` (or `cli attribute`) to record real cost against it; read cost
  with `cli trace`. Documents the exact recipe + "definition of done". Explicitly states it
  is advisory (a skill cannot block; the only hard gates are couche-0 PreToolUse/CI).
- A SHORT, optional note may be added to existing agent prompts ("if a board exists, work
  against the active in-progress US") — advisory only, no token self-reporting claim.
- NO Stop/SessionEnd auto-hook, NO new consumer-shipped hook.

### F. Docs
- `dashboard/README.md`: a self-contained "Track the cost of a US" walkthrough + the new
  endpoints/CLI. Skill docs. Root README/CHANGELOG.

## Acceptance criteria
- `board.costs()` rollup correct (US→Feature→Epic) with per-agent breakdown; `/api/board/costs`.
- `cli trace` + `/api/trace` flatten work_log; `--us` filters.
- `subagent_runs()` reconciles: `attributed + unattributed == by_source subagent total`
  (a test asserts no double-count); identity from toolUseResult + meta; never crashes on a
  missing/odd `toolUseResult` (defensive parse, skip non-`completed`/missing-usage).
- `cli link` is idempotent per `(session_id, us_id)` and emits per-(source/agent) entries;
  `WorkLogEntry` has `source` + `subagent_type`.
- pricing strips `[..]` tier suffix.
- Skill present (SKILL.md + VERIFY.md); tests green; ruff+mypy clean; docs updated.

## Out of scope (deferred, named)
- Any auto/mid-run trace writer; the Stop/SessionEnd hook; "force" gating.
- Consumer-repo cost tracking / fleet aggregation.
- Tier-accurate long-context pricing (only the suffix is stripped; premium not modeled).
- Splitting one session across multiple US (a linked session attaches to one US).
