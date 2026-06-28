---
name: us-cost-tracking
description: Use when you want delivery work tracked as Agile items with REAL token/cost attribution on the Fenrir dashboard — represent a task as a User Story on the board, then record what each agent/subagent actually spent against it and read the cost trace. Triggers — "track the cost of this US", "how much did this task cost", "log this work to the board", "cost trace", "which subagent spent what". NOT a hard gate (a skill cannot block — couche-0 PreToolUse/CI are the only gates); NOT for a prose session digest (use `report`); NOT for fleet/multi-repo cost (out of scope). Needs the companion `dashboard/` app; no org-profile keys required.
---

# US Cost Tracking

The working contract for **costed delivery**: substantive work is a **User Story** on the
board, and real spend (input/output tokens + USD, per agent and per subagent) is attributed
to it from telemetry. This is **advisory — encourage + record, not force**: a skill cannot
block anything (the only hard gates are couche-0 PreToolUse hooks + CI). What it gives you
is one honest place to answer "what did this US cost, and which agent/subagent spent it".

## When to use
- "track / cost this task", "how much did this US cost", "log this work", "show the cost trace"
- You are delivering through `/fenrir:deliver` (or by hand) and want per-US, per-agent cost.

## When NOT to use
- As a merge/▮block gate → it is advisory; couche-0 (PreToolUse + CI required-checks) blocks.
- Cross-repo / fleet cost aggregation → out of scope (single repo + its dashboard).
- The per-call token/cost *meter* → that is the dashboard `telemetry` + `pricing` modules.

## Inputs
- The companion `dashboard/` app (its `backend.cli` + `data/board.json`). No `org-profile.yaml` keys.
- A Claude Code session id (for attribution) — the current session's transcript under `~/.claude`.

## The formalism (definition of done for a costed US)
1. **Represent the work** — create the Epic → Feature → User Story before coding:
   `python -m backend.cli story add --feature <id> --title "…" --assignee <agent> --points N`
2. **Move it** as you work: `… move --kind story --id us-N --status in_progress` (→ `review` → `done`).
3. **Attribute real cost** after a stage/session (this is the record step):
   `python -m backend.cli link --kind story --id us-N --session <session-id>`
   — pulls the session's REAL tokens/cost from telemetry, writes one work-log entry per
   source (main vs subagent). Idempotent per (session, US): re-running is a no-op.
4. **Identify subagents** — `GET /api/telemetry/subagents` (or the dashboard Subagents panel)
   shows which named subagent ran, when, on what, and how much (reconciled, no double-count).
5. **Read the trace** — `python -m backend.cli trace --us us-N` (or `/api/trace`,
   `/api/board/costs`) for the per-US, per-agent breakdown.

## Steps (when asked to cost a task)
1. If no board item exists for the task, create the Epic/Feature/US (step 1 above); set status.
2. Run the work (delegate to agents as usual).
3. `link` the session to the US to record real spend; confirm with `trace`.
4. Report the US cost + per-agent/subagent breakdown.

## Output / validation
- A US on the board with a `work_log` whose tokens/cost come from real telemetry, plus a
  chronological cost trace. Validate: `cli trace --us <id>` totals match `/api/board/costs`
  for that US; subagent attribution reconciles (attributed + unattributed == subagent total).

## Refuses when
- Asked to present this as a hard cost gate that blocks merges/runs (it is advisory).
- Asked to fabricate token/cost numbers instead of attributing them from real telemetry.
- Asked to aggregate cost across multiple repos (out of scope).

## Sources
- `dashboard/README.md` (the "Track the cost of a US" walkthrough + API/CLI reference).
