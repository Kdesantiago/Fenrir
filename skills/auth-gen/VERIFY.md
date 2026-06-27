# VERIFY — auth-gen

Run after `auth-gen` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] OIDC/OAuth2 middleware glue was emitted for the declared provider+framework: login redirect, callback handler, and token/JWT validation are all present in the generated module
- [ ] output matches `org-profile.yaml`: `auth_provider` is one of entra/okta/keycloak/auth0 AND `framework` is set — the generated code uses THAT provider's vetted library (no wrong-provider, no hand-rolled token/crypto)
- [ ] no secrets in source: issuer/client-id/client-secret all read from ENV/config — `! grep -rEi '(client_secret|client_id|issuer)\s*[:=]\s*["'\''][^"'\'' $]+' <generated-dir>`
- [ ] output is marked REQUIRING human review and was NOT auto-injected into a protected/middleware path

## Informational (tooling presence — does NOT block; note if absent)
- [ ] the provider's vetted auth library installed for the framework (e.g. MSAL / authlib / passport) → note absent, don't fail

## Functional
- The generated middleware loads against the provider's OIDC discovery document (well-known config resolves) and conforms to the framework's middleware contract; the review checklist is present and unchecked.
