# VERIFY — us-cost-tracking

Run after costing a User Story with the dashboard. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the work is represented on the board: `python -m backend.cli list` shows the Epic → Feature → US for the task (run from `dashboard/`)
- [ ] real cost is attributed, not fabricated: the US `work_log` came from `cli link --session <id>` (telemetry-sourced), and re-running the same `link` is a no-op (idempotent per session+US)
- [ ] subagent attribution reconciles (no double-count): for `/api/telemetry/subagents`, `attributed_tokens + unattributed_tokens == subagent_total_tokens`
- [ ] the trace agrees with the rollup: `cli trace --us <id>` total matches `/api/board/costs` `stories[<id>].cost_usd`

## Informational (does NOT block; note if absent)
- [ ] the companion app runs: `cd dashboard && uv run uvicorn backend.app:app` serves `/api/board/costs`, `/api/trace`, `/api/telemetry/subagents`
- [ ] cost is understood as a derived ESTIMATE (price book in `dashboard/backend/pricing.py`), not billed dollars

## Functional
- Create a US, `link` a session to it → the US shows per-agent (main vs subagent) tokens + $.
- `cli trace --us <id>` lists the entries chronologically with a matching total.
- The Subagents view names which subagent ran, when, and how much, summing to the attributed total.

## Honesty boundary
- This skill RECORDS and REPORTS cost; it does not BLOCK anything. The only hard gates are
  couche-0 (PreToolUse hooks + CI required-checks). Do not present a cost number as a gate.
