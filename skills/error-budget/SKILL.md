---
name: error-budget
description: Use when you want an SRE error-budget POLICY plus its delivery gate — define a service's SLO + error budget, then generate a CI check and branch-protection wiring so that, once a rolling four-week burn exhausts the budget, only critical and security patches may ship while everything else waits, with normal releases resuming when the SLI recovers to target. NOT for defining the metrics pipeline (observability-gen). Reads org-profile.yaml `obs_backend` (where SLO/error metrics live) and refuses without it.
---

# Error Budget

## When to use
- "define the SLO and error budget for this service"
- "wire the error-budget freeze into CI / branch protection"
- You want delivery cadence tied to SLOs, not to a calendar

## When NOT to use
- Defining the metrics pipeline / how SLIs are emitted → use `observability-gen`
- Generic lint/type/test feedback on a diff → use `delivery-gates`
- No declared `obs_backend` → this skill refuses (it can't query the budget)

## Inputs
- `org-profile.yaml` → `obs_backend` (REQUIRED — where SLO/error metrics live: query Prometheus/Grafana, Azure Monitor, Datadog, etc.)
- The service's target SLO (provided or inferred from existing SLIs)

## Steps
1. Read `org-profile.yaml`; resolve `obs_backend`. If unset, REFUSE.
2. Write the error-budget POLICY: the SLO, the budget derived from it, the rolling **four-week** window, the freeze rule (while the budget is exhausted only **critical/security** patches ship — everything else waits), and the unfreeze condition (SLI recovered to target).
3. Generate the CI check: a script that queries `obs_backend` for the service's error rate over the rolling four-week window, computes budget burn, and exits non-zero when the budget is exhausted — emitting a clear over/under-budget verdict.
4. Generate branch-protection wiring that adds this check as a **required status check** so non-critical, non-security releases cannot merge while it fails.
5. State explicitly: this skill WRITES the policy + the check. The freeze itself is enforced by the CI required-check + branch-protection (**couche 0**), not by the skill. Without that wiring installed (`repo-bootstrap`), nothing is actually frozen.

## Output / validation
- An error-budget policy doc + a runnable CI budget-check + the branch-protection required-check wiring
- Verify the check queries `obs_backend` and flips pass/fail across the budget threshold on test data; verify the check is listed as required on the protected branch
- Authoritative enforcement is the CI required-check + branch-protection, NOT this skill — extends the `delivery-gates` model (ties cadence to SLOs)

## Refuses when
- `org-profile.yaml` is missing, or `obs_backend` is unset (no source to query the budget)
- Asked to define how the SLI/error metrics are produced (route to `observability-gen`)
- Asked to claim the skill itself blocks releases — the freeze is a CI/branch-protection control, and the output must say so

## Sources
- https://sre.google/workbook/error-budget-policy/
