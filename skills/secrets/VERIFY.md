# VERIFY — secrets

Run after `secrets` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] reference wiring matches `org-profile.yaml` `platform` (right mechanism, no wrong one):
  - `aks`/`k8s` → a `SecretProviderClass` (Azure Key Vault provider) + workload-identity binding exist (`grep -rl 'SecretProviderClass' .`)
  - `webapp` → App Service `app_settings` use `@Microsoft.KeyVault(...)` references + a managed identity (`grep -r '@Microsoft.KeyVault' .`)
  - git-stored config → SOPS-encrypted file + `.sops.yaml` with `age` recipients exist
- [ ] NO literal secret values committed anywhere — every secret resolves from the store at runtime: `! grep -rEi '(password|secret|token|api[_-]?key)\s*[:=]\s*["'\''][^"'\'' $@]+' --include='*.yaml' --include='*.yml' --include='*.env' .` (and `gitleaks detect` is clean)
- [ ] a rotation cadence is documented per secret (owner + interval + where rotation happens)
- [ ] wrapper-aware mode (when `stack-interface.yaml` exists): Vault/login commands came from `stack-adapter`, not raw `az keyvault`/`az login`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v gitleaks` · `command -v sops` · `command -v age` · `command -v az` → note absent, don't fail

## Functional
- The reference resolves at runtime for an authorized identity: the CSI mount populates / `@Microsoft.KeyVault(...)` resolves to a value / `sops -d <file>` succeeds — and `gitleaks` reports zero committed secrets.
