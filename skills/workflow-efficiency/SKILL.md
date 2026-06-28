---
name: workflow-efficiency
description: Use when authoring or reviewing a multi-agent workflow (the Workflow tool / fan-out) for COST and SPEED — tier the model per stage, budget prompts (pass file refs, not inlined blobs), keep prefixes cache-stable, cap fan-out. Triggers — "this workflow costs too much", "speed up the fan-out", "which model for this stage", "reduce agent token spend". NOT for product LLM context (context-engineering), NOT for runtime spend alerts (llm-cost-monitor), NOT for a single LLM-call wrapper (llm-gen). Advisory — the dashboard cache-efficiency view measures the result.
---

# Workflow Efficiency — cheap-but-good multi-agent runs

The bill on a multi-agent run is **context volume × model tier**, re-read across many calls — not
the cache (cache-read is already 0.1× input; it SAVES ~10×, it is not the waste). So the levers
are about how you *construct* the fan-out. This skill is advisory: it changes how you author a
workflow; the `dashboard` **cache-efficiency** view (hit-ratio, actual-vs-uncached) tells you
whether it worked.

## When to use
- "this workflow / fan-out is too expensive or too slow", "reduce agent token spend"
- "which model tier for this stage", "should this be Opus or Haiku"
- Reviewing a `Workflow` script before running it at scale

## When NOT to use
- Designing the PRODUCT's LLM context window / retrieval ordering → `context-engineering`
- Runtime LLM spend monitoring, budgets, alerts → `llm-cost-monitor`
- A single typed LLM call wrapper → `llm-gen`
- Correctness/quality review of the workflow's OUTPUT → `reviewer` / `red-team-destroyer`

## Inputs
- The `Workflow` script (or the plan for one): its stages, fan-out width, and per-agent prompts.
- The `dashboard` cache-efficiency + by-model views to see where spend + low hit-ratio land (optional but recommended).

## Steps
1. **Tier the model per stage (biggest $ lever).** Mechanical stages — structured extraction, convention/lint checks, applying a known fix, format-preserving edits — run on **Haiku** (`$1/$5`, cache-read `$0.10`) or **Sonnet** (`$3/$15`). Reserve **Opus** for genuine judgment: design, red-team, synthesis, ambiguous triage. (`opts.model` / `opts.effort` per `agent()` call.) Opus-everywhere is the #1 overspend.
2. **Budget the prompt.** Do NOT inline large blobs (full specs / inventories / conventions) into *every* agent prompt — write them to a file once and pass the **path**; the agent reads only the slice it needs. Inlining multiplies cache-write + cache-read by the fan-out width.
3. **Keep prefixes cache-stable.** Put the large, identical context FIRST and vary only the tail per agent, so N agents share one cache write + cheap reads instead of N distinct writes.
4. **Right-size the fan-out.** Cap agent count to the real work-list; batch items into one agent when each is tiny; bound loop-until-dry with K. Spawning 100 agents where 10 suffice is 10× the context.
5. **Tier effort, not just model.** `effort: 'low'` for cheap mechanical stages; reserve `high`/`max` for the hardest verify/judge stages.
6. **Measure.** After a run, open the dashboard cache-efficiency view: a stage/agent-type with high spend and a LOW hit-ratio is re-sending fresh context — fix it with steps 2–3.

## Output / validation
A workflow whose stages declare an intentional model/effort tier, pass context by reference, and
cap fan-out — and a before/after read on the dashboard (actual cost down, hit-ratio up). This is
guidance, not a gate: nothing forces a workflow to be efficient; the measurement just makes waste
obvious. Validate with `VERIFY.md`.

## Refuses when
- Asked to make a workflow cheaper by cutting correctness gates (verify/red-team stages) — efficiency never trades away the quality bar; tier the model, don't drop the check.
- Asked to design product retrieval/context (→ `context-engineering`) or build spend alerting (→ `llm-cost-monitor`).
