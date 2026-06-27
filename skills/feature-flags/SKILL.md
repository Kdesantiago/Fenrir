---
name: feature-flags
description: Use when you need centralized runtime feature-flag management to decouple RELEASE from DEPLOYMENT — a shared flag store (Azure App Configuration via the Python feature-management library) with kill-switches, percentage flighting, and targeting. Triggers — "add feature flags", "kill-switch for a feature", "roll a feature out to 5% of users then ramp". NOT for secret storage (use `secrets` / Key Vault) and NOT for the rollout traffic-shift mechanism (use `progressive-delivery`). Reads org-profile.yaml `platform`/`framework` (FastAPI/Streamlit); refuses on mismatch.
---

# Feature Flags

This skill is advisory — it scaffolds the flag store + the client wiring + a flag taxonomy. It does NOT enforce that flags are used correctly; the runtime control plane is Azure App Configuration itself (couche-0). The point is to **decouple release from deployment**: ship code dark, flip it on at runtime per environment / per user %, and kill it instantly without a redeploy.

## When to use
- "add feature flags", "centralized flag store", "kill-switch for a feature"
- "roll a feature out to 5% of users first, then ramp" (canary-style via flighting, no traffic mesh)
- Decouple deploy from release for the FastAPI / Streamlit Python stack across the org's multi-repo model

## When NOT to use
- Storing secrets / connection strings / keys → `secrets` skill (Key Vault); App Configuration is NOT a secret store
- Shifting infra traffic between pod versions with metric-gated promotion → `progressive-delivery` (flighting here is app-level, not pod-level)
- Static per-environment config that never flips at runtime → plain env/values (no flag store needed)
- `platform`/`framework` not in the supported (k8s/aks + Python FastAPI/Streamlit) shape → refuse

## Inputs
- `org-profile.yaml` → `platform` and `framework` (expects the FastAPI/Streamlit Python stack)
- `org-profile.yaml` → `environments` (the declared list, e.g. `[dev, staging, prod]`) → become App Configuration **labels** (do not hardcode; read the profile)
- The flags + their type (boolean kill-switch, percentage flighting, targeting filter)
- `stack-interface.yaml` (OPTIONAL) → get App Configuration endpoint/auth from the `stack-adapter` agent, not raw `az appconfig`

## Steps
1. Read `org-profile.yaml`; resolve `platform`/`framework`. If the stack is not the supported Python (FastAPI/Streamlit) shape, REFUSE.
2. **Flag store** — provision/reference an **Azure App Configuration** store as the single shared source of flags. Access via **managed identity** (no connection-string literal); if `stack-interface.yaml` exists, get the endpoint/auth through `stack-adapter` (`MISSING-MAPPING` → use the standard Azure SDK `DefaultAzureCredential` against the endpoint and note no wrapper was declared).
3. **Per-environment labels** — store each flag under one label per declared `environments` entry; the app selects its label from its environment so the same key resolves differently per env.
4. **Client wiring** — use the official Python **`featuremanagement`** library (with `azure-appconfiguration-provider`):
   - **FastAPI**: load + refresh the provider at startup; gate endpoints/branches with `feature_manager.is_enabled("Flag")`.
   - **Streamlit**: resolve flags at session start; gate UI sections.
   - Provider refresh (sentinel-key polling) so flips take effect at RUNTIME without redeploy.
5. **Percentage flighting** — configure the percentage filter so a flag targets a small user % first, then ramps (canary-style release) — independent of how the pods were deployed.
6. **Kill-switch** — a boolean flag flipped in App Configuration disables the feature live; the running app picks it up on refresh. State the max propagation delay (refresh interval).
7. **Targeting filters** — target groups/users (internal first, then cohorts) via the targeting filter for staged rollout.

## Output / validation
- An App Configuration store reference + the Python client wiring (`featuremanagement` + provider, managed-identity auth) + per-env labels + the flag set (kill-switches, percentage filters, targeting filters) + a short flag taxonomy/runbook.
- Validation: no secrets in App Configuration (those route to `secrets`/Key Vault); auth is managed-identity, never a literal connection string; flags resolve per `dev/staging/prod` label; provider refresh is enabled so flips are runtime; flighting/targeting filters parse.

## Refuses when
- `org-profile.yaml` missing, or `platform`/`framework` not the supported Python (FastAPI/Streamlit) stack.
- Asked to store secrets/keys/connection strings as feature flags — refuse and redirect to the `secrets` skill / Key Vault.
- App Configuration access would use a literal connection string instead of managed identity.

## Sources
- https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-feature-management
