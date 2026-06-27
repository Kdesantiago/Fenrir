# VERIFY — gitops

Run after `gitops` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] operator bootstrap IaC exists (Flux `microsoft.flux` extension / Argo CD): `grep -rEq 'azurerm_kubernetes_(cluster_extension|flux_configuration)|microsoft.flux|fluxConfigurations|argo-?cd' . && echo OK || echo MISSING`
- [ ] structured config repo skeleton present: `[ -d clusters ] && [ -d apps ] && echo OK || echo MISSING` (and `infrastructure/`; reconciliation order infra→apps)
- [ ] CI≠CD: the pipeline builds+pushes to ACR and bumps the manifest tag but holds NO cluster creds — `grep -rEq 'az acr|docker push|ImageUpdateAutomation|imagePolicy' . && ! grep -rEq 'kubectl apply|kubeconfig|az aks get-credentials' .github .azure* azure-pipeline*.yml 2>/dev/null && echo OK || echo CI-LEAKS-CLUSTER-CREDS`
- [ ] (profile-driven) `platform` in `org-profile.yaml` is `aks`/`k8s` and image automation is scoped to the declared `container_registry`/ACR repo

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v flux` · `command -v az` · `command -v kubectl` · `command -v terraform` → note absent, don't fail

## Functional
- `terraform validate` (or Bicep build) passes on the extension IaC, and the operator reconciles the config repo (pull-only) — out-of-band `kubectl` edits revert to Git state.
