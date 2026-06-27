# VERIFY — iac-gen

Run after `iac-gen` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] artifacts match the declared `platform` from `org-profile.yaml` (right stack, NO wrong-stack artifacts):
  - `k8s`/`aks` → `[ -f */Chart.yaml ] || [ -f chart/Chart.yaml ]` AND an ArgoCD `Application` manifest AND a pipeline template exist
  - `webapp` → App Service IaC (`azurerm_service_plan` + `azurerm_linux_web_app` + a `staging` slot) exists AND **no** Helm/k8s manifests were emitted (`! ls -d */templates/*.yaml 2>/dev/null | grep -q .`)
- [ ] per-environment values/params split exists (e.g. `values-dev.yaml`/`values-prod.yaml` or per-env App Service settings) with NO hardcoded secrets — `! grep -rEi '(password|secret|api[_-]?key)\s*[:=]\s*["'\''][^"'\'' ]+' <generated-dir>`
- [ ] `aks`-specific (when platform is `aks`): workload-identity SA annotation, ACR pull role assignment, and Azure CNI are all present in the chart/IaC
- [ ] wrapper-aware mode (when `stack-interface.yaml` exists): every cloud command came from `stack-adapter` — `! grep -rE '\b(az|kubectl|helm|terraform) ' <pipeline>` finds raw CLI calls

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v helm` · `command -v terraform` · `command -v az` · `command -v bicep` → note absent, don't fail

## Functional
- `k8s`/`aks`: `helm lint <chart>` and `helm template <chart>` succeed and the ArgoCD manifest references valid paths. `webapp`: `terraform validate` (or `bicep build`) passes cleanly on the generated IaC.
