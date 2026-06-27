# VERIFY — progressive-delivery

Run after `progressive-delivery` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a `Rollout` CRD replaced the bare Deployment, with exactly one `canary` OR `blueGreen` strategy block: `f=$(grep -rl 'kind: Rollout' . | head -1); [ -n "$f" ] && grep -Eq 'strategy:|canary:|blueGreen:' "$f" && echo OK || echo MISSING`
- [ ] an `AnalysisTemplate` exists and references a REAL metric query, with `successCondition` + `failureLimit`: `f=$(grep -rl 'kind: AnalysisTemplate' . | head -1); [ -n "$f" ] && grep -Eq 'successCondition|failureLimit' "$f" && echo OK || echo MISSING`
- [ ] the Rollout references the AnalysisTemplate AND `trafficRouting` points at the real Service(s)/ingress (no hand-rolled `setWeight` without analysis gating)
- [ ] (profile-driven) every analysis query targets the `obs_backend` from `org-profile.yaml` (prometheus/azure-monitor) and `platform` is `aks`/`k8s` — no wrong-provider analysis emitted

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v kubectl` · `command -v kubeconform` · `kubectl argo rollouts version` (or flagger) → note absent, don't fail

## Functional
- `kubectl apply --dry-run=server` (or `kubectl argo rollouts lint` / `kubeconform`) passes on the Rollout + AnalysisTemplate, and the preview/stable services resolve.
