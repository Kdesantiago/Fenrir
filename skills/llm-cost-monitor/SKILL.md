---
name: llm-cost-monitor
description: Use when you need to MONITOR and BUDGET LLM spend — per-route/per-model cost attribution, budget thresholds with alerts, cost dashboards, and spend-anomaly detection, wired through the declared obs_backend. NOT the per-call token/cost ACCOUNTING itself (that's llm-gen — cross-ref, don't reimplement). Reads org-profile.yaml llm_provider + obs_backend and refuses without llm_provider.
---

# LLM Cost Monitor

Scoped to **monitoring + budgeting**, built ON TOP of the per-call accounting that `llm-gen` already produces. This skill does not meter individual calls (that's `llm-gen`) and it does not enforce a hard cap — alerts/dashboards are observational; a true budget kill-switch is app/infra logic, not a skill.

## When to use
- "monitor LLM cost", "alert when we blow the token budget", "build a cost dashboard / detect a spend spike"
- You already have per-call token/cost numbers from `llm-gen` and want them attributed, budgeted, and watched

## When NOT to use
- The per-call token/cost tracker itself → `llm-gen` (this skill CONSUMES its counters)
- General app/infra metrics + OTel init → `observability-gen`
- Shaping prompts to spend fewer tokens (compression, budgeting per section) → `context-engineering` agent
- No declared `llm_provider` → this skill refuses

## Inputs
- `org-profile.yaml` → `llm_provider` (anthropic | openai | azure | bedrock | vertex) — REQUIRED, sets the price book (per-model input/output token prices; `azure` = Azure OpenAI deployment pricing)
- `org-profile.yaml` → `obs_backend` — where cost metrics/traces land (`langfuse` = LLM cost/traces, ideal here; otherwise emit standard cost metrics to the declared backend). Endpoint/keys from ENV/config only.

## Steps
1. Read `org-profile.yaml`; resolve `llm_provider`. If unset or `none`, REFUSE.
2. Consume `llm-gen`'s per-call token/cost counters as the source of truth — do NOT re-implement token counting or pricing math here. Verify current model prices and the `obs_backend` cost-tracking API (Langfuse cost/usage, etc.) against current docs before wiring (prices and SDKs change often).
3. **Cost attribution** — tag every call with `route`/endpoint and `model` (and optionally team/tenant) so spend rolls up per-route and per-model.
4. **Budget thresholds + alerts** — define budgets (daily/monthly, per route or model) and alert at soft/hard thresholds via the backend's alerting; thresholds from config.
5. **Dashboards** — cost over time, by model, by route, top spenders; on `langfuse` use its cost/usage views, else build the panels on the declared backend.
6. **Spend-anomaly detection** — flag deviations from the rolling baseline (sudden token-per-request growth, a route's cost spike, retry storms) so a runaway loop is caught early.
7. Wire all of it through `obs_backend` via ENV/config — never hardcode the backend endpoint/key.

## Output / validation
- Cost-attribution tags + budget/alert config + dashboards + anomaly rules, fed by `llm-gen`'s counters and exported via `obs_backend`
- Validate: a sample run shows cost attributed per route+model, a forced over-budget run fires the alert, an injected spike trips anomaly detection; switching `obs_backend` is ENV/config-only
- This is observational. A hard budget cap (refuse the call when over budget) is application/infra control, not this skill — recommend wiring it there if needed

## Refuses when
- `llm_provider` is unset or `none` in `org-profile.yaml`
- Asked to BE the per-call cost tracker (route to `llm-gen`) or to hardcode the backend endpoint/key
