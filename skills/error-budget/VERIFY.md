# VERIFY — error-budget

Run after `error-budget` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] an SLO + error-budget POLICY exists with the rolling four-week window, the freeze rule (all but P0/security) and the unfreeze condition: `grep -rEqi 'slo|error budget|four-?week|freeze|p0' . && echo OK || echo MISSING`
- [ ] a runnable CI budget-check script queries the metrics backend, computes burn, and exits non-zero when exhausted: `f=$(grep -rEl 'error.budget|burn.rate|budget.check' . | head -1); [ -n "$f" ] && grep -Eq 'exit 1|sys.exit|return 1' "$f" && echo OK || echo MISSING`
- [ ] branch-protection wiring adds the budget-check as a REQUIRED status check — and the doc states the CI required-check is the real gate, NOT the skill: `grep -rEqi 'required.status.check|branch protection|required_checks' . && echo OK || echo MISSING`
- [ ] (profile-driven) the check queries the `obs_backend` named in `org-profile.yaml` (right metrics backend), not a hardcoded other source

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v` the metrics backend CLI (promtool / az monitor / datadog) · `command -v gh` → note absent, don't fail (freeze goes live only after branch-protection is applied)

## Functional
- On seeded data the check flips pass/fail across the budget threshold (exit 0 under budget, non-zero over), and it is listed as a required check on the protected branch.
