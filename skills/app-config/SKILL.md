---
name: app-config
description: >-
  Use when typing the `core/` config layer — one `pydantic-settings` BaseSettings
  object with `env_prefix`, required fields that fail-fast at import/boot,
  validators, a `.env.example` kept in sync, and feature-flag DECLARATION.
  Triggers — "add a setting / env var", "type the config", "read this from .env",
  "validate config on boot", "wire a feature flag". NOT for secret STORAGE/rotation
  (use `secrets` / Key Vault), NOT for business logic (use domain-services), NOT for
  the runtime flag STORE/targeting mechanism (use `feature-flags`) — app-config only
  declares + reads the flag. Refuses-when asked to design (→ architect) or to
  gate/merge (→ reviewer) or to touch a gate file (.claude/, CI). Reads
  org-profile.yaml `framework` (FastAPI/Streamlit); refuses off-stack.
---

# app-config — the typed `core/` settings layer

This skill is the implementer for the `core/{settings,config}.py` layer (ADR-0005): one typed settings object, fail-fast on boot, `.env.example` in sync, feature flags declared. It is ZERO-cloud — it works with no `az`/`terraform`/`gh`. The core rule: **config is typed and validated at the boundary, and a missing required value fails at import/boot, never at first use** — no scattered `os.getenv`, no literal secrets, no untyped string config.

## When to use
- "add a setting / env var", "type the config", "read this from `.env`"
- "validate config on boot", "fail fast if config is wrong"
- "wire / declare a feature flag" (the typed default + where-it-comes-from note — NOT the store)

## When NOT to use
- Secret STORAGE / rotation / KV references → `secrets` (Key Vault is its lane; app-config only READS the resolved value from ENV)
- Business logic / use-cases → domain-services (config is read, not computed)
- The runtime flag STORE + targeting/flighting mechanism → `feature-flags` (App Config service); app-config only DECLARES the flag + its typed default

## Inputs
- `org-profile.yaml` → `framework` (FastAPI/Streamlit) — REQUIRED; refuse off-stack.
- The variable(s)/flag(s) to add: name, type, required-or-defaulted, any constraint (URL, enum, range, port).
- `org-profile.yaml` → `cloud_layer` (OPTIONAL) — only when `azure`, the Azure App Configuration pointer below applies; otherwise ignored entirely.

## Steps
1. **Read `org-profile.yaml`; resolve `framework`.** If unset or off-stack, REFUSE — do not hardcode config.
2. **One typed settings object.** `pydantic-settings` `BaseSettings`, `env_prefix="<MODULE>_"`, reads `.env` (ADR-0005). Imported as `from core.settings import settings` — a singleton, no re-instantiation.
3. **Type + default every field.** Required fields get **no** default so a missing one fails **at import/boot**, not at first use. Add validators for constrained values (URLs, enums, ranges, ports).
4. **No scattered `os.getenv`.** Convert every stray `getenv` in the module into a typed field on the settings object — the settings object is the one source.
5. **Secrets via ENV/config, never literal.** No secret string in source; the value arrives through ENV (resolved by `secrets`/KV upstream). Keep `.env.example` documenting every var (prefix-correct) **in sync** with the model.
6. **No import-time side effects.** No network/DB call at import; constructing settings only reads env + defaults.
7. **Feature flags = DECLARE only.** Each flag is a typed field with a default (off by default) + a one-line "where the value comes from" note; safe to remove. The store/targeting is `feature-flags`' job.

## Output / validation
- A typed settings object + a synced `.env.example`: every field typed, required fields default-less (boot fails on absence), validators on constrained values, flags declared with typed off-defaults, zero stray `getenv`, zero literal secrets.
- Validation: import the module with a required var UNSET and confirm it raises at import/boot (not first use); import with all vars set and confirm `settings` constructs; grep the module for `os.getenv`/`os.environ` outside `settings.py` (must be empty); confirm every `env_prefix`-correct var in the model appears in `.env.example` and vice versa.
- Boundary: this skill declares + reads config; it does NOT store secrets (`secrets`) or run the flag store (`feature-flags`). The teeth are the fail-fast boot check + the VERIFY greps.

## Optional Azure layer (one-line pointer, opt-in)
When `org-profile.yaml` `cloud_layer: azure`, source flag VALUES from **Azure App Configuration** (feature-management lib) with an ENV-driven endpoint — never hardcoded; consult `feature-flags`. The Azure layer never loads or blocks for a local user; the core ships with no `az`/`terraform`.

## Refuses when
- `org-profile.yaml` missing, or `framework` not the supported (FastAPI/Streamlit) shape.
- Asked to STORE a secret or wire rotation/KV (→ `secrets`), or to run the flag store/targeting (→ `feature-flags`).
- A literal secret would land in source instead of arriving via ENV/config.
- Asked to design the config architecture (→ architect) or to gate/merge (→ reviewer), or to touch a gate file (`.claude/`, CI).
