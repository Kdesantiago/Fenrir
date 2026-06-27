---
name: auth-gen
description: Use when you need OIDC/OAuth2 middleware glue for the org's DECLARED auth provider (entra/okta/keycloak/auth0) in the declared framework. NOT for SSO product features unrelated to delivery. Reads org-profile.yaml auth_provider + framework and refuses without both.
---

# Auth Generator

## When to use
- "wire up OIDC/OAuth2 middleware" for the provider declared in the profile
- You need login/callback/token-validation glue bound to the org's vetted auth library

## When NOT to use
- Building end-user SSO product features (account linking UI, tenant admin) unrelated to delivery scaffolding
- No declared provider/framework yet → this skill refuses
- App business logic → use the relevant app/framework generator

## Inputs
- `org-profile.yaml` → `auth_provider` (entra | okta | keycloak | auth0) — REQUIRED
- `org-profile.yaml` → `framework` — REQUIRED

## Steps
1. Read `org-profile.yaml`; resolve `auth_provider` and `framework`. If either is missing, REFUSE.
2. Select the provider's vetted/org-approved auth library for the framework; prefer it over hand-rolled token logic.
3. Generate OIDC/OAuth2 middleware glue: login redirect, callback handler, token/JWT validation, session wiring.
4. Read all secrets/issuer/client config from ENV/config — never literal in source.
5. Emit the output marked as REQUIRING human review before merge; do not auto-inject into protected paths.

## Output / validation
- Provider-specific middleware glue + config wiring + a review checklist
- Verify against the provider's OIDC discovery document and the framework's middleware contract
- SECURITY: output is advisory scaffolding — a human MUST review auth before it ships; never auto-inject unreviewed auth

## Refuses when
- `auth_provider` or `framework` is unset in `org-profile.yaml`
- The declared provider is not one of entra/okta/keycloak/auth0
- Asked to hand-roll bespoke token/crypto logic when a vetted library exists
