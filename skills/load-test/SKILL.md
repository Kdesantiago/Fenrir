---
name: load-test
description: Use when you need synthetic load/performance scenarios to exercise canary gates + SLOs BEFORE prod — "load test this service", "add a k6/Locust scenario", "spike/soak test", "validate the SLO thresholds under load". Picks k6 (default), Locust, or Azure Load Testing per repo. NOT the canary/rollout mechanism (use `progressive-delivery`) and NOT the SLI/SLO definitions (use `observability-gen`). Reads org-profile.yaml `platform` + `framework`; refuses without `framework`.
---

# Load Test

This skill generates the SYNTHETIC LOAD that validates a service's gates pre-prod. It does not gate a rollout (that is `progressive-delivery`, which consumes REAL prod metrics) and it does not define the SLIs/SLOs (that is `observability-gen`). It reuses those SLO targets as test thresholds so a regression fails the run.

## When to use
- "load test this endpoint/service", "add a performance scenario", "spike/soak/baseline test"
- "make sure our canary gates + SLOs actually trip before we ship to prod"
- You have SLIs/SLOs from `observability-gen` and want them exercised under generated traffic

## When NOT to use
- The canary / blue-green rollout that gates on real metrics → `progressive-delivery`
- Defining the SLI queries / SLO targets / alert rules → `observability-gen` (this skill consumes them)
- Fast local lint+type+test on a diff → `delivery-gates`
- No declared `framework` → this skill refuses

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED (shapes the target endpoints / app entrypoint)
- `org-profile.yaml` → `platform` — selects the runner default (e.g. Azure stacks may use Azure Load Testing)
- The SLOs from `observability-gen` (p99 latency, error rate, saturation) — reused as test thresholds
- Target base URL / route(s) under test and expected steady-state RPS

## Steps
1. Read `org-profile.yaml`; resolve `framework`. If unset, REFUSE.
2. Pick the tool per repo: **k6** (default), **Locust**, or **Azure Load Testing** config (favored when `platform` is an Azure stack). Do not mix.
3. Generate three scenarios:
   - **baseline** — steady target RPS at expected load, held long enough to read p99/error rate.
   - **spike** — sharp ramp to a multiple of baseline then back, to test elasticity / autoscale / backpressure.
   - **soak** — modest RPS held for a long duration, to surface leaks / saturation drift.
4. **Thresholds = SLOs** — encode the `observability-gen` SLO targets as pass/fail thresholds (k6 `thresholds` / Locust assertions / Azure Load Testing pass-fail criteria): p99 latency, error rate, and a saturation signal. A breach FAILS the run (non-zero exit) so a regression is caught pre-prod.
5. Wire the run into CI as a pre-prod check (against staging, not prod), surfacing the threshold result.

## Output / validation
- A runner config (k6 script / Locust file / Azure Load Testing YAML) with baseline + spike + soak scenarios and SLO-aligned thresholds
- Verify: a deliberately slow/erroring target makes the run exit non-zero (the threshold actually fails); thresholds match the `observability-gen` SLO numbers
- Generates load only — it never promotes/rolls back a deployment

## Refuses when
- `framework` is unset in `org-profile.yaml`
- Asked to BE the canary / rollout / auto-promotion mechanism, or to gate on production traffic → route to `progressive-delivery`
- Asked to invent SLO targets instead of reusing `observability-gen`'s → route to `observability-gen`

## Sources
- https://grafana.com/docs/k6/latest/
- https://docs.locust.io/
- https://learn.microsoft.com/azure/load-testing/
