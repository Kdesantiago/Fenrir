# VERIFY — workflow-efficiency

Run after `workflow-efficiency` has shaped a multi-agent workflow. All BLOCKING checks must pass.

## Blocking (the workflow is not efficiency-shaped if any fail)
- [ ] **Model tiering is intentional, not Opus-everywhere:** at least the mechanical stages (extraction / convention-check / apply-fix / format edits) declare a cheaper tier (`opts.model` Haiku or Sonnet, or `opts.effort: 'low'`), and Opus is reserved for judgment stages. A script where every `agent()` is implicit-Opus with no `model`/`effort` on any mechanical stage FAILS.
- [ ] **No large blob inlined per agent:** the per-agent prompt does not `JSON.stringify` a full spec/inventory/convention set into every agent. Large shared context is written to a file once and passed by PATH (agents read their slice). Grep the script for a big `JSON.stringify(` inside the per-item `agent()` callback — if the shared payload is inlined into every agent, FAIL.
- [ ] **Fan-out is bounded:** the item list is the real work-list (or batched), and any loop-until-dry has a K bound — no unbounded/oversized spawn.
- [ ] **Correctness gates preserved:** efficiency changes did not remove a verify / red-team / test stage (tier its model, don't delete it).

## Informational (does NOT block; note if absent)
- [ ] prefixes are cache-stable (large identical context first, only the tail varies per agent)
- [ ] `dashboard/` is present so the cache-efficiency view can measure the result
- [ ] a before/after note records actual cost + cache hit-ratio for the changed workflow

## Functional
Run the workflow once, then open the dashboard **cache-efficiency** view (`/api/telemetry/efficiency`)
scoped to this project. Confirm the changed stages show a higher cache hit-ratio and lower actual
cost than before, with no regression in the workflow's output quality (the verify/red-team stages
still run and still pass).
