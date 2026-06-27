---
name: iac-gen
description: Use when you need profile-driven infrastructure-as-code for a Kubernetes (`k8s`/`aks`), Azure Web App (`webapp`), serverless, vm, or ecs repo — Helm chart / App Service IaC + env values + ArgoCD app (where applicable) + pipeline template. NOT for application code (use the app/framework generators). Reads org-profile.yaml platform and refuses on any platform the profile does not declare or that is unset. Wrapper-aware: when stack-interface.yaml exists, gets concrete cloud commands from the stack-adapter agent instead of emitting raw az/kubectl.
---

# IaC Generator

## When to use
- "scaffold the Helm chart / ArgoCD app / deploy pipeline" for a service where `platform` is `k8s` or `aks`
- "scaffold the Azure Web App / App Service IaC + slots" where `platform: webapp`
- Infra for `serverless` / `vm` / `ecs` repos the profile declares
- You need vendor-neutral env values split (per-environment) and a pipeline template

## Supported `platform` values
`k8s` · `aks` (Azure Kubernetes Service) · `webapp` (Azure App Service / Web App) · `serverless` · `vm` · `ecs`. The skill generates ONLY for the value the profile declares (see "Refuses when").

## When NOT to use
- Generating application/business logic → use the relevant app/framework generator (`frontend-gen`, etc.)
- `platform` is unset, or is a value this skill does not support, or differs from what you were asked to emit → this skill refuses; never force the wrong stack (e.g. Helm) into the repo
- Initializing repo tooling/CI gates → use `repo-bootstrap`

## Inputs
- `org-profile.yaml` → `platform` (REQUIRED; must be one of the supported values above)
- Service metadata from the profile/repo for naming and image references
- `stack-interface.yaml` (OPTIONAL) → presence switches the skill into wrapper-aware mode (see below)

## Wrapper-awareness (cloud commands)
Before emitting any concrete cloud command (login, ACR build/push, `aks-get-credentials`, deploy, rollback) or any IaC backend/auth invocation in the pipeline:
- **If `stack-interface.yaml` exists:** do NOT emit raw `az` / `terraform` / `bicep` / `kubectl` / `helm`. Delegate to the **`stack-adapter`** agent to obtain the company's exact wrapper command sequence, and embed those commands verbatim in the pipeline/templates. If the adapter returns `MISSING-MAPPING`, surface it and stop — do not substitute a raw CLI.
- **If absent:** use the standard CLIs (`az`, `terraform`/`bicep`, `docker`, `kubectl`, `helm`) directly.

## Steps
1. Read `org-profile.yaml`; resolve `platform`. If unset, unsupported, or different from what you were asked to emit, REFUSE immediately (never scaffold the wrong stack — e.g. Helm into a Lambda/VM/webapp repo).
2. Check for `stack-interface.yaml`; set wrapper-aware vs standard-CLI mode (see above). Resolve cloud commands through `stack-adapter` when wrapper-aware.
3. Branch by `platform`:
   - **`k8s`** — Helm chart (`Chart.yaml`, templates, sane `values.yaml`) + ArgoCD app + pipeline (existing behavior).
   - **`aks`** (Azure Kubernetes Service) — Helm chart with AKS specifics:
     - **Workload identity**: ServiceAccount annotated with the client-id; the federated credential / `azurerm_federated_identity_credential` + user-assigned identity in IaC (no static secrets).
     - **Ingress**: AGIC (Application Gateway Ingress Controller) or the AKS app-routing add-on; emit the matching `Ingress`/annotations.
     - **Image pull from ACR**: reference `container_registry`; pull via the cluster's kubelet/managed identity (AcrPull role assignment in IaC), not imagePullSecrets where avoidable.
     - **Networking**: Azure CNI (not kubenet) in the cluster config.
     - **Cluster IaC**: Terraform `azurerm_kubernetes_cluster` (+ node pools, identity, ACR role assignment) — or the wrapper's IaC tool when `stack-interface.yaml` is present.
     - Plus ArgoCD app + pipeline; `aks-get-credentials` / ACR push / deploy commands obtained from `stack-adapter` when wrapper-aware.
   - **`webapp`** (Azure App Service / Web App — NOT Kubernetes; emit NO Helm/k8s manifests):
     - **App Service plan** + the web app: Terraform `azurerm_service_plan` + `azurerm_linux_web_app` (or Bicep).
     - **Deployment slots**: a `staging` slot with **staging→swap** to production (`azurerm_linux_web_app_slot` + a swap step in the pipeline).
     - **Container vs code deploy**: pick per profile/repo — container image from `container_registry`, or zip/code (`SCM_DO_BUILD_DURING_DEPLOYMENT`).
     - **App settings / secrets**: `app_settings` with **Key Vault references** (`@Microsoft.KeyVault(...)`) + a managed identity; never literal secrets.
     - Pipeline does build → (push to ACR for container) → deploy to staging slot → swap; deploy/swap commands via `stack-adapter` when wrapper-aware.
   - **`serverless` / `vm` / `ecs`** — emit the matching infra for that target (no Helm); same wrapper-awareness and per-env split apply.
4. Generate per-environment values/parameter files (e.g. `values-dev.yaml`/`values-prod.yaml`, or per-env App Service settings) with no hardcoded secrets.
5. For chart-based platforms (`k8s`/`aks`), generate an ArgoCD `Application` manifest pointing at the chart + env values.
6. Generate the pipeline template (build/push/deploy/swap) wired to the target, using wrapper or standard commands per mode.

## Output / validation
- **`k8s`/`aks`**: Helm chart + env values + ArgoCD app + pipeline template. Verify with `helm lint` and `helm template`; ArgoCD manifest must reference valid paths. For `aks` also confirm workload-identity SA annotation, ACR pull role, and Azure CNI are present.
- **`webapp`**: App Service plan + web app (+ staging slot) IaC + per-env settings + pipeline (deploy-to-slot → swap). Verify the IaC plans cleanly (`terraform validate`/Bicep build, or the wrapper's plan) and that no Helm/k8s manifests were emitted.
- Secrets/config injected via values/ENV/Key Vault references, never literal in templates.
- When wrapper-aware: every cloud command in the output came from `stack-adapter` (no raw `az`/`kubectl`/`terraform`).

## Refuses when
- `org-profile.yaml` missing, or `platform` unset, unsupported, or different from what you were asked to emit
- Asked to emit infra for a stack the profile does not declare (never emit wrong-stack code — e.g. Helm for a `webapp` profile)
- Wrapper-aware mode and `stack-adapter` returns `MISSING-MAPPING` for a required cloud op — stop, do not fall back to a raw CLI
