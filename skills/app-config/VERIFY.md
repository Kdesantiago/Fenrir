# VERIFY — app-config

Run after `app-config` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **settings module** — `core/settings.py` (or `core/config.py`) — not the whole repo. A repo-wide search is not falsifiable (a stray `BaseSettings` import or a `.env` line would pass with zero real config). Resolve the settings file(s) first, then run the co-located checks:

```
CFG_FILES=$(grep -rlE 'BaseSettings|SettingsConfigDict|pydantic_settings' --include='*.py' . )
echo "${CFG_FILES:-<none — settings module not found, FAIL>}"
ENV_EXAMPLE=$(ls .env.example **/.env.example 2>/dev/null | head -1)
```
If `CFG_FILES` is empty, the skill produced no typed settings object → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **typed BaseSettings with env_prefix** — one object, prefix set: `for f in $CFG_FILES; do grep -qE 'class .*\(BaseSettings\)' "$f" && grep -qE 'env_prefix' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING`
- [ ] **fail-fast: at least one required (default-less) field** so a missing var raises at import/boot: `for f in $CFG_FILES; do grep -nE '^\s+[a-z_]+\s*:\s*[A-Za-z]' "$f" | grep -vE '=|Field\(' && echo "REQUIRED-FIELD in $f"; done; for f in $CFG_FILES; do grep -E '^\s+[a-z_]+\s*:\s*[A-Za-z]' "$f" | grep -vqE '=|Field\(' && echo OK; done | grep -q OK && echo OK || echo NO-REQUIRED-FIELD`
- [ ] **no scattered getenv** — config reads go through the settings object, not raw env, OUTSIDE the settings file: `OTHERS=$(grep -rlE 'os\.getenv|os\.environ' --include='*.py' . | grep -vFf <(printf '%s\n' $CFG_FILES) ); [ -z "$OTHERS" ] && echo OK || { echo "STRAY-GETENV in $OTHERS"; echo MISSING; }`
- [ ] **no literal secret in source** (hard fail): `! grep -rEq '(password|secret|api_key|token|access_key)\s*[:=]\s*["'\''][^"'\''$@{][^"'\'']+["'\'']' $CFG_FILES && echo OK || echo SECRET-LITERAL-FOUND`
- [ ] **`.env.example` present and prefix-correct** — documents the vars (no real values): `[ -n "$ENV_EXAMPLE" ] && grep -qE '^[A-Z][A-Z0-9_]+=' "$ENV_EXAMPLE" && echo OK || echo MISSING-ENV-EXAMPLE`
- [ ] **singleton import shape** — settings consumed as `from core.settings import settings`, not re-instantiated per-call: `grep -rqE 'from core\.settings import settings|^settings\s*=\s*Settings\(' $CFG_FILES && echo OK || echo MISSING`
- [ ] (profile-driven) `framework` in `org-profile.yaml` is the supported (FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] **feature-flag declared with a typed default** (off by default) when a flag was the ask — advisory: `for f in $CFG_FILES; do grep -qE '(enable|feature|flag)_[a-z_]+\s*:\s*bool\s*=\s*False' "$f" && echo "flag declared"; done || echo "NOTE: no typed off-by-default flag found — confirm none was requested"`
- [ ] `python -c 'import pydantic_settings'` → note absent, don't fail
- [ ] **Azure layer is opt-in only** — if `cloud_layer: azure`, an App Configuration/feature-management pointer may be present; its ABSENCE never fails (core is zero-cloud): `grep -rEq 'AzureAppConfiguration|feature_management|azure\.appconfiguration' . && echo "azure app-config wiring present" || echo "NOTE: no Azure App Config wiring — expected for a local/zero-cloud user"`

## Functional
Import the settings module with a required var UNSET and confirm it raises at import/boot (`ValidationError`), not at first use; then set every var and confirm `settings` constructs cleanly; finally confirm every `env_prefix`-correct field in the model has a matching line in `.env.example` and vice versa (the example is in sync, with no real secret values) — none of the three should require any `az`/network call.
