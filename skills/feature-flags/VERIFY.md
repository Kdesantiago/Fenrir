# VERIFY — feature-flags

Run after `feature-flags` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] client wired via the official Python feature-management lib (not a hand-rolled flag dict): `grep -rEq 'featuremanagement|azure-appconfiguration-provider|FeatureManager|is_enabled' . && echo OK || echo MISSING`
- [ ] flags reference Azure App Configuration with per-env labels (one per declared `environments` entry, e.g. `dev`/`staging`/`prod`) and provider refresh enabled: `grep -rEq 'AppConfiguration|app(_|-)?config|select\(.*label|refresh' . && echo OK || echo MISSING`
- [ ] NO secrets in flags and NO literal connection string — auth is managed identity: `! grep -rEq 'Endpoint=https://.*;Id=.*;Secret=|password|api[_-]?key' . && grep -rEq 'DefaultAzureCredential|ManagedIdentity' . && echo OK || echo SECRET-OR-CONNSTR-FOUND`
- [ ] (profile-driven) `platform`/`framework` in `org-profile.yaml` is the supported Python (FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` (`az appconfig` extension) · `python -c 'import featuremanagement'` → note absent, don't fail

## Functional
- The app resolves a kill-switch flag per `dev/staging/prod` label and a percentage/targeting filter parses; flipping the boolean in App Configuration disables the feature live within the refresh interval (no redeploy).
