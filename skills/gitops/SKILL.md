---
name: gitops
description: Use when you need a pull-based GitOps delivery loop for AKS/k8s — an in-cluster operator (Flux v2 default, or Argo CD) reconciling the cluster to a Git config repo, with CI and CD split so build agents never get cluster creds. Triggers — "set up GitOps / Flux / Argo CD", "pull-based delivery", "CI pushes the image, the cluster pulls". NOT for generating the infra itself (use `iac-gen`) and NOT for the rollout/metric-gating strategy (use `progressive-delivery`). Reads org-profile.yaml `platform` (aks/k8s; refuses otherwise).
---

# GitOps

This skill is advisory — it scaffolds the operator config + repo layout + pipeline split. The real gate is the in-cluster reconciler (Flux/Argo CD), installed by couche-0 infra; nothing here enforces "Git is the source of truth" except the operator itself running in the cluster. The skill's job is to wire **pull-based** delivery correctly: no cluster endpoint is exposed to build agents, and drift is reconciled continuously.

## When to use
- "set up GitOps for this AKS cluster", "Flux / Argo CD pull-based delivery"
- "the build pipeline should push the image and bump the manifest, the cluster should pull" (CI/CD split)
- You have infra from `iac-gen` but no delivery loop closing Git → cluster

## When NOT to use
- Generating the cluster / Helm chart / App Service IaC → `iac-gen` (it makes infra, not the GitOps loop)
- Canary / blue-green + metric-gated promotion → `progressive-delivery` (rides on top of this loop)
- `platform` is not `aks`/`k8s` → refuse (no pull-based k8s operator for webapp/serverless/vm/ecs)

## Inputs
- `org-profile.yaml` → `platform` (REQUIRED; `aks` or `k8s` only)
- The config repo URL + the app/image being delivered (+ `container_registry` for ACR)
- IaC tool in use (Terraform azurerm / Bicep / az CLI) for enabling the extension
- `stack-interface.yaml` (OPTIONAL) → get cluster/extension/ACR commands from the `stack-adapter` agent, not raw `az`/`kubectl`/`flux`

## Steps
1. Read `org-profile.yaml`; resolve `platform`. If unset or not `aks`/`k8s`, REFUSE. Pick the operator: **Flux v2** (default) or **Argo CD** if declared.
2. **Enable the operator as an AKS cluster extension** (Flux = `microsoft.flux`):
   - **Terraform**: `azurerm_kubernetes_cluster_extension` + `azurerm_kubernetes_flux_configuration`.
   - **Bicep**: `Microsoft.KubernetesConfiguration/extensions` + `.../fluxConfigurations`.
   - **az CLI**: `az k8s-extension create` + `az k8s-configuration flux create`.
   - **At scale**: apply the extension/config across clusters with **Azure Policy** (so new clusters onboard automatically), not per-cluster clicks.
3. **Structure the Git config repo** — `clusters/` (per-cluster Kustomizations / Flux sources), `apps/` (workload manifests/Helm releases), `infrastructure/` (controllers, ingress, policies). Reconciliation order: infrastructure → apps.
4. **SPLIT CI from CD** (the core safety property):
   - **CI** (Azure DevOps or GitHub Actions): build the image, push to **ACR**, then bump the manifest/image tag in the config repo (commit/PR). The build agent never gets cluster credentials.
   - **CD**: the in-cluster operator **pulls** the config repo and reconciles — no cluster endpoint or kubeconfig is exposed to the pipeline.
5. **Image-update-automation**: Flux `ImageRepository` + `ImagePolicy` + `ImageUpdateAutomation` (or Argo CD Image Updater) to auto-bump tags from ACR within policy, writing back to Git.
6. **Drift detection**: operator reconciles continuously; out-of-band `kubectl` edits are reverted to the Git state. Surface drift/health (Flux `Kustomization` ready conditions; alert via `observability-gen`/`obs_backend`).
7. **Deploy/bootstrap**: if `stack-interface.yaml` exists, route extension-enable / ACR / bootstrap commands through `stack-adapter` (`MISSING-MAPPING` → emit the standard `az k8s-extension` / `flux bootstrap` command and note no wrapper was declared). Otherwise use the standard CLIs.

## Output / validation
- Operator extension IaC + Flux/Argo configuration + config-repo skeleton (`clusters/ apps/ infrastructure/`) + a CI pipeline that builds/pushes to ACR and bumps the tag (with NO cluster credentials) + image-update-automation manifests.
- Validation: IaC plans cleanly (`terraform validate` / Bicep build); the pipeline contains no kubeconfig/`kubectl apply` to the cluster (pull-only); reconciliation order is infra→apps; image automation scoped to the right ACR repo. Pairs with `iac-gen` (infra) and `progressive-delivery` (rollout strategy).

## Refuses when
- `org-profile.yaml` missing, or `platform` unset / not `aks`/`k8s`.
- Asked to make the pipeline `kubectl apply`/push directly to the cluster — refuse; that breaks the pull-based model and hands cluster creds to a build agent.
- No Git config repo is provided — there is no source of truth to reconcile against.

## Sources
- https://learn.microsoft.com/en-us/azure/architecture/example-scenario/gitops-aks/gitops-blueprint-aks
