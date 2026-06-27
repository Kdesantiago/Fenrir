# VERIFY — load-test

Run after `load-test` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a runner config exists for ONE chosen tool — k6 script, Locust file, or Azure Load Testing YAML — not a mix
- [ ] all three scenarios present: baseline (steady RPS), spike (ramp up then down), and soak (held duration) — each distinguishable in the config
- [ ] thresholds encode the `observability-gen` SLOs: p99 latency, error rate, AND a saturation signal are all asserted (k6 `thresholds` / Locust assertions / Azure Load Testing pass-fail criteria)
- [ ] a threshold breach FAILS the run (non-zero exit) — the config aborts/fails on SLO violation, it does not just report
- [ ] runs against staging / a non-prod target, NOT production; the config does not promote or roll back any deployment
- [ ] matches `org-profile.yaml`: tool default consistent with `platform`; the target shape matches the declared `framework`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v k6` · `command -v locust` · the Azure Load Testing extension/resource (whichever tool was chosen) → note absent, don't fail

## Functional
- Point a scenario at a deliberately slow/erroring target → the run exits non-zero because a threshold fails. Confirm the threshold numbers equal the `observability-gen` SLO targets (not invented), and that the run only generates load — it never calls a promote/rollback API.
