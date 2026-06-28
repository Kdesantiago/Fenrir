---
name: optimize
description: Use when optimizing code under ONE stated constraint — latency, throughput, memory, cost, bundle-size, or cold-start (cost = per-call compute/runtime cost of THIS path; NOT LLM spend → llm-cost-monitor, NOT delivery/agent cost → us-cost-tracking). Measure-first — baseline, change, re-measure, PROVE the delta; refuses an unmeasured "optimization". Triggers — "make this faster/cheaper/smaller", "reduce p99 / cold-start". NOT a load profile (load-test), NOT no-perf-goal cleanup (fenrir:refactor). Reads org-profile.yaml `framework`/`platform`; refuses without a constraint.
---

# Optimize — measure, change, prove

Performance work under **exactly one** stated constraint, proven by a recorded before/after benchmark. The discipline is measure-first: no number, no claim. This skill *advises and demonstrates* a delta on your machine; it is not a perf gate — the deterministic guard against regressions is the CI benchmark / load-test threshold (couche-0), not this skill. An optimization with no measured improvement beyond variance is reverted, not shipped.

## When to use
- "make this faster / cheaper / lighter / smaller", "reduce p99 latency / memory / cold-start", "optimize throughput", "shrink the bundle"
- You have a measurable hot path and a single clear target metric to beat
- You want a proven before/after benchmark, not a hunch

## When NOT to use
- You need a load profile or to drive traffic at a service → `load-test` (its run is the baseline workload this skill measures against — it generates load, it does not change code)
- Behavior-preserving restructuring with no perf target → `fenrir:refactor` (it cleans up; it has no constraint and records no benchmark)
- Monitoring / budgeting LLM spend in production → `llm-cost-monitor` (ongoing spend telemetry, not a one-shot code change)
- No single stated constraint, or no way to measure it → this skill refuses (optimization without a benchmark is forbidden)

## Inputs
- The ONE stated constraint: `latency | throughput | memory | cost | bundle-size | cold-start` — REQUIRED. Refuse if absent, or if several are named without a declared primary.
- `org-profile.yaml` → `framework` + `platform` — selects the benchmark harness for that constraint and stack:
  - latency/throughput (Python) → `pytest-benchmark` / `timeit`; web → wrk/k6 single-route probe
  - memory → `memory_profiler` / `tracemalloc`
  - bundle-size (front) → bundler stats (`vite build` / `webpack-bundle-analyzer` / `source-map-explorer`)
  - cold-start (serverless/functions) → a cold-invoke probe on `platform`
  - cost → per-call compute-cost = measured runtime (from the latency harness above) × the `platform` instance `$`/s (e.g. function GB-s price, vCPU-hour ÷ 3600); or a cloud billing/cost export scoped to the code path when one exists. If neither the runtime nor a `$`/s rate for `platform` can be obtained, refuse — `cost` has no baseline.
- A representative workload/input (or a `load-test` profile) to measure against — the baseline is meaningless without realistic load.

## Steps
1. **Resolve the single constraint.** Confirm exactly one metric to optimize and its target. If none is stated, or several with no primary, REFUSE and ask for one + its target number. One constraint is optimized; trade-offs against the others are reported, not silently accepted.
2. **Pick the harness from the profile.** Read `org-profile.yaml` `framework`/`platform`; choose the matching harness for that constraint+stack (see Inputs). If the declared stack cannot be measured for that metric, refuse rather than fake a number.
3. **Record the BEFORE baseline.** Run the benchmark N times (≥5; report median + variance, not a single sample). Capture the metric, the variance/stddev, and the **exact command** so it is reproducible. No baseline → no optimization.
4. **One hypothesis, minimal change.** Profile to locate the bottleneck; cite `file:line` / profiler output. Form ONE hypothesis and apply the smallest change that targets it (e.g. eager-load to kill an N+1, memoize a hot call, lazy-import to cut cold-start). Do NOT blanket-rewrite — a diffuse rewrite makes the delta unattributable.
5. **Assert behavior unchanged.** Run the full test suite; reuse the `fenrir:refactor` before/after guardrail (same tests green before and after). A perf win that changes outputs or breaks tests is rejected — that is a behavior change, not an optimization.
6. **Re-measure with the SAME harness.** Run the identical command from step 3 N times. Report before/after, the %delta, and whether the constraint target was met. If the improvement is within noise/variance, REVERT and report honestly that there was no win.
7. **Emit the benchmark report.** Metric, before, after, %delta, exact command, plus a behavior-unchanged attestation. Note trade-offs against the OTHER constraints (e.g. memory up to cut latency) so the cost of the win is explicit.

## Output / validation
- A benchmark report: `metric | before | after | %delta | command`, the variance for both runs, and a behavior-unchanged attestation (test suite identical before/after).
- The minimal code change tied to the one hypothesis, with the `file:line` bottleneck it targets.
- Validate: re-running the recorded command reproduces the after-number within variance; `pytest` (or the repo runner) is green; the claimed delta exceeds measured noise.
- This is advisory proof on your machine — the durable guard is a CI benchmark / `load-test` SLO threshold; wire one if regressions must be blocked at merge.

## Refuses when
- No single constraint is stated, or several are named with no declared primary.
- `framework`/`platform` is unset in `org-profile.yaml`, or the declared stack cannot be measured for the requested metric.
- A baseline cannot be recorded (no representative workload / harness) — optimization without a benchmark is forbidden.
- The change alters behavior (test suite differs before vs after) — that is a behavior change, route to `fenrir:refactor` or `architect`.
- The re-measure shows no improvement beyond variance — revert and say so; do not claim an unproven win.
