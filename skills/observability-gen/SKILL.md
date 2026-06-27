---
name: observability-gen
description: Use when you need vendor-neutral OpenTelemetry SDK init, semantic conventions, async resilience patterns (timeout/retry/backpressure), AND the SLI/SLO definitions + alert rules for the declared backend. NOT for app business logic. Reads org-profile.yaml obs_backend + framework; exporter is wired via ENV/config, never hardcoded.
---

# Observability Generator

## When to use
- "add OpenTelemetry instrumentation", "wire tracing/metrics/logs" for the declared framework
- You need standard async patterns: timeouts, retries with backoff, backpressure
- You want semantic conventions applied consistently across services
- "define the SLO/SLI", "add alert rules" — author the SLI queries, SLO targets, and alert rules that `progressive-delivery` (analysis), `error-budget` (burn), and `incident-runbook` (paging) consume

## When NOT to use
- Application/business logic → use the relevant app/framework generator
- A vendor-specific agent install with no code instrumentation → out of scope; keep it vendor-neutral
- No declared framework → this skill refuses

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED
- `org-profile.yaml` → `obs_backend` — selects the exporter, wired via ENV/config only

## Steps
1. Read `org-profile.yaml`; resolve `framework`. If unset, REFUSE.
2. Generate OpenTelemetry SDK init for the framework (tracer/meter/logger providers, resource attributes).
3. Apply OTel semantic conventions for spans/metrics/attributes.
4. Generate async resilience patterns: timeout wrappers, retry-with-backoff, backpressure/bounded concurrency.
5. Wire the `obs_backend` exporter strictly via ENV/config (OTLP endpoint, headers) — NEVER hardcode the backend.
   - **`langfuse` = LLM tracing/evals** (not infra metrics): wire Langfuse over OTLP (or its SDK) to trace LLM calls — prompt, model, token usage, latency, cost, eval scores. Pairs with `llm-gen` (feed its cost/token tracking into Langfuse). Host + keys from ENV (`LANGFUSE_HOST`/keys); self-hosted or cloud. For non-LLM infra metrics still emit standard OTel to your metrics backend.
6. **SLIs / SLOs / alert rules** (the signals downstream skills consume): author the SLI queries (latency p99, error rate, saturation) in the declared `obs_backend`'s query language (PromQL for `grafana`/`prometheus`/`azure-monitor` managed Prometheus; the vendor equivalent otherwise), the SLO targets, and the alert rules (Prometheus alerting rules / Grafana alerts / Azure Monitor alert rules). These are the inputs `progressive-delivery` (AnalysisTemplate), `error-budget` (burn query), and `incident-runbook` (paging) read.

## Output / validation
- OTel init module + semantic-convention helpers + async patterns + ENV-driven exporter config + SLI/SLO + alert rules
- Verify spans/metrics export to a local OTLP collector; resource attributes populate correctly
- Switching `obs_backend` requires only ENV/config changes, no code edits

## Refuses when
- `framework` is unset in `org-profile.yaml`
- Asked to hardcode a backend endpoint/key instead of reading ENV/config
