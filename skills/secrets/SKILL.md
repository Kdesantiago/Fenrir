---
name: secrets
description: Use when you need to MANAGE secret references — wire Key Vault / SOPS references, set a rotation cadence, enforce no-literal-at-rest. NOT for scanning for leaked secrets (the gitleaks pre-commit hook + delivery-guard own that). Wires secret refs for the declared platform (Azure Key Vault via CSI driver / App Service references; SOPS+age for git-stored config), never literal values. Reads org-profile.yaml `platform` + `auth_provider`; uses stack-adapter for KV/login commands when stack-interface.yaml exists.
---

# Secrets

## When to use
- "wire up Key Vault references", "set up the Secrets Store CSI driver", "encrypt this config with SOPS"
- "define a rotation cadence", "make sure no secret literals are committed"
- A service needs its secrets injected from a store at runtime for the declared `platform`

## When NOT to use
- Scanning the diff/history for leaked credentials → NOT this skill; the pre-commit `gitleaks` hook + `delivery-guard` own detection
- SAST / dependency / threat review → `security-review`
- Supply-chain pinning / SBOM / license policy → `deps`

## Inputs
- `org-profile.yaml` → `platform` (REQUIRED: `aks`/`k8s` vs `webapp` selects the wiring) and `auth_provider` (e.g. `entra` → managed identity / workload identity binds the app to the Vault)
- `stack-interface.yaml` (OPTIONAL) → when present, get concrete KV / login commands from the `stack-adapter` agent instead of emitting raw `az keyvault` / `az login`
- The set of secret names the service consumes (names only — never values)

## Steps
1. Read `org-profile.yaml`; resolve `platform` + `auth_provider`. If `platform` is unset, REFUSE.
2. If `stack-interface.yaml` exists, resolve all Vault/login/CLI commands through `stack-adapter` (embed verbatim; on `MISSING-MAPPING`, stop). Otherwise use standard `az`/SOPS CLIs.
3. Wire references for the platform — never literal values:
   - **`aks`/`k8s`** → Secrets Store CSI driver `SecretProviderClass` (Azure Key Vault provider) + workload identity (the app's ServiceAccount federated to a Key Vault access policy / RBAC); secrets mounted/synced, not baked into the image or manifests.
   - **`webapp`** → App Service Key Vault references in `app_settings` (`@Microsoft.KeyVault(...)`) + the app's managed identity granted `get` on the Vault.
   - **git-stored encrypted config** → SOPS with `age` recipients; commit only the encrypted file, decrypt at deploy/runtime.
4. Enforce the no-literal rule: every secret resolves from the store at runtime; nothing secret is committed to code, values files, or env files.
5. Define the rotation cadence per secret (owner + interval) and document where rotation happens (Vault rotation / re-key SOPS recipients).

## Output / validation
- A `SecretProviderClass` + workload-identity binding (`aks`/`k8s`), or Key Vault-referenced `app_settings` + managed identity (`webapp`), or SOPS-encrypted config (+ `.sops.yaml`) — plus a documented rotation cadence
- Verify: no plaintext secret appears in the repo (`gitleaks` clean), and the reference resolves at runtime (CSI mount populated / `@Microsoft.KeyVault` resolves / `sops -d` succeeds for an authorized key)
- This skill wires references and defines cadence; it does NOT detect leaks — the `gitleaks` pre-commit hook + `delivery-guard` are the enforcing gate for committed secrets

## Refuses when
- Asked to write a literal secret value into code, a values/env file, or any committed config
- `platform` is unset / undeclared (cannot choose the correct wiring)
- `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING` for a required Vault op — stop, do not fall back to a raw CLI
