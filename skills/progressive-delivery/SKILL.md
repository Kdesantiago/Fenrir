---
name: progressive-delivery
description: Use when you need automated, metric-gated progressive rollout (canary / blue-green) for an AKS/k8s workload — a Rollout CRD plus the metric-analysis that drives promotion or rollback (Argo Rollouts default, or Flagger). Triggers — "canary/blue-green this service", "add metric-gated promotion with auto-rollback on bad metrics". NOT for the GitOps delivery loop (use `gitops`) and NOT for hand-rolled traffic shifting. Reads org-profile.yaml `platform` (aks/k8s only) + `obs_backend` (metric source); refuses otherwise.
---

# Progressive Delivery

This skill is advisory — it generates the rollout + analysis config; it does NOT itself gate a deploy. The real gate is the controller (Argo Rollouts / Flagger) running in the cluster, which the couche-0 infra installs. The skill's job is to wire the **metric-analysis mechanism** correctly so promotion/rollback is automated and driven by real signals — not to hand-roll traffic percentages.

## When to use
- "do a canary / blue-green rollout for this AKS service with automatic rollback on bad metrics"
- "add metric-gated promotion (error rate / latency) to the deploy"
- You have a cluster (`iac-gen`) and a delivery loop (`gitops`) and now need the rollout strategy on top

## When NOT to use
- The pull-based GitOps delivery loop itself (Flux/Argo CD reconcile, repo structure) → `gitops`
- Plain k8s `Deployment` rolling update with no metric gate → not progressive delivery; just deploy
- Emitting the metrics/SLOs the analysis queries → `observability-gen`
- `platform` is not `aks`/`k8s` → refuse (no progressive-delivery scaffold for webapp/serverless/vm/ecs)

## Inputs
- `org-profile.yaml` → `platform` (REQUIRED; `aks` or `k8s` only) and `obs_backend` (REQUIRED; the metric source the AnalysisTemplate queries)
- The workload (Deployment/Service) being rolled out + its success metrics (error rate, latency p95, custom)
- Traffic provider in use (ingress controller / SMI mesh / Gateway API)
- `stack-interface.yaml` (OPTIONAL) → get cloud/cluster commands from the `stack-adapter` agent, not raw `kubectl`/`az`

## Steps
1. Read `org-profile.yaml`; resolve `platform`. If unset or not `aks`/`k8s`, REFUSE (see below). Resolve `obs_backend` — it determines the AnalysisTemplate provider.
2. Pick the controller: **Argo Rollouts** (default) or **Flagger** if the profile/repo declares it. Do not mix.
3. **Rollout CRD** — emit a `Rollout` (replacing the bare `Deployment`) with **ONE** strategy (Argo's `spec.strategy` is canary XOR blueGreen — never both on one Rollout). Pick by the task:
   - **canary**: stepped `setWeight` + `pause`, each step gated by an analysis run; abort → rollback to stable.
   - **blue-green**: `activeService`/`previewService`, `prePromotionAnalysis` + `postPromotionAnalysis`, `autoPromotionEnabled` driven by the analysis result.
4. **Analysis** — emit `AnalysisTemplate`(s) the rollout references so promotion/rollback is AUTOMATED, not manual:
   - **prometheus / grafana**: `provider.prometheus` with the query (e.g. `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))`), `successCondition`, `failureLimit`, `interval`, `count`.
   - **azure monitor**: provider querying Azure Monitor / Managed Prometheus metrics for the same SLI.
   - A failed `AnalysisRun` aborts the rollout and rolls back to stable automatically — state this is the gate.
5. **Traffic management** — wire the rollout's `trafficRouting` to the provider in use (ingress: nginx/AGIC; SMI: e.g. Linkerd/Open Service Mesh; Gateway API: `HTTPRoute`). The controller shifts weight; the skill does NOT compute or hand-roll the shift.
6. **Deploy** — if `stack-interface.yaml` exists, route cluster credential / apply commands through `stack-adapter` (`MISSING-MAPPING` → emit the standard `kubectl apply` / `kubectl argo rollouts` command and note no wrapper was declared). Otherwise use the standard CLIs.

## Output / validation
- A `Rollout` (canary + blue-green strategy blocks) + `AnalysisTemplate`(s) with concrete `obs_backend` queries + traffic-routing config, referencing the existing Service(s)/ingress.
- Validation: `kubectl apply --dry-run=server` (or `kubectl argo rollouts lint`) passes; every analysis query targets the declared `obs_backend`; failureLimit/successCondition set so a bad run actually aborts; preview/stable services resolve. Pairs with `iac-gen` (cluster), `gitops` (delivery loop), `observability-gen` (the metrics).

## Refuses when
- `org-profile.yaml` missing, or `platform` unset / not `aks`/`k8s` (no progressive-delivery scaffold for other platforms).
- `obs_backend` unset or has no usable metric source — there is nothing to gate promotion on; an analysis-less "progressive" rollout is just a slow deploy.
- Asked to hand-roll traffic-percentage shifting instead of delegating it to the controller — refuse; that defeats the automated-analysis mechanism.

## Sources
- https://argoproj.github.io/rollouts/
- https://learn.microsoft.com/en-us/azure/architecture/example-scenario/gitops-aks/gitops-blueprint-aks
