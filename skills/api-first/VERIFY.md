# VERIFY — api-first

Run after `api-first` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] spec is the source of truth and lints clean: `[ -f api/openapi.yaml ] && [ -f api/.spectral.yaml ] && echo OK || echo MISSING`, then `spectral lint api/openapi.yaml --ruleset api/.spectral.yaml` passes
- [ ] REST conventions hold in the spec: plural-noun resources, no verbs in paths, `/v1` prefix, RFC 9457 `application/problem+json` error envelope, `securitySchemes` from `auth_provider` — Spectral's custom rules (no-verbs-in-paths, versioned-paths, problem+json, operationId, pagination) all green
- [ ] codegen matches `org-profile.yaml` `framework`: stubs/typed client generated FROM the spec (fastapi → Pydantic models + routers; else openapi-generator) — and contract tests + `templates/ci/api-contract.yml` were copied into the repo's CI dir
- [ ] every generated handler corresponds to a spec operation (no undocumented routes); a coverage note lists handled vs still-stubbed operations

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v spectral` · `command -v schemathesis` (Python) or `command -v dredd` · `command -v openapi-generator` → note absent, don't fail

## Functional
- Start the generated app and run the contract test (Schemathesis/Dredd) against it: it passes and flags no undocumented routes or spec↔impl drift.
