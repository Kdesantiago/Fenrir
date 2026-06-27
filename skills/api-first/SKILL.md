---
name: api-first
description: Use when designing or building an HTTP API contract-first — write/extend the OpenAPI spec BEFORE code, enforce REST conventions, then generate server stubs + typed client + contract tests from the spec. Triggers — "design this API", "add a REST endpoint", "API-first", "OpenAPI/Swagger", "what should the contract be". NOT for consuming a third-party API, NOT for GraphQL/gRPC (out of scope), NOT for non-HTTP. Reads org-profile.yaml `framework`.
---

# API-First

Contract before code. The **OpenAPI 3.1 spec is the source of truth**; server, client, and tests are generated/validated against it — never the reverse. The skill works spec-first and pushes you to add an operation to the spec before its handler; the *enforcement* of that (catching undocumented routes / spec↔impl drift) is the contract-test CI job, not a promise the skill can keep alone.

## When to use
- "design the API for X", "add a REST resource/endpoint", "review my API for REST correctness"
- Starting a new service's HTTP surface, or extending an existing `openapi.yaml`

## When NOT to use
- Calling/consuming someone else's API → just write a client, no contract authoring here
- GraphQL or gRPC → out of scope (different contract model; say so and stop)
- Non-HTTP transport, or internal function calls

## Inputs
- `org-profile.yaml` → `framework` (fastapi | express | spring | …) drives codegen target
- `auth_provider` → the spec's `securitySchemes` (OIDC/OAuth2 bearer)
- An existing `api/openapi.yaml` if the service already has one (extend, don't replace)

## Steps
1. **Contract first** — write/extend `api/openapi.yaml` (OpenAPI 3.1). Define: resources as `components/schemas`, paths, request/response bodies, and:
   - **Error model**: `application/problem+json` (RFC 9457) — `type/title/status/detail/instance`. One envelope, everywhere.
   - **Security**: `securitySchemes` from `auth_provider` (bearer/OIDC); mark protected operations.
   - **Versioning**: path prefix `/v1`. Breaking change → `/v2`, never mutate `/v1`.
   - **Collections**: pagination (cursor or `page`/`size`), `sort`, and `filter` query conventions — consistent across all list endpoints.
   - **Idempotency**: `Idempotency-Key` header on non-idempotent POSTs that may be retried.
2. **REST review** (block on violation):
   - Resources are **plural nouns**, no verbs in paths (`/orders/{id}` not `/getOrder`).
   - Verbs/status: `GET`→200/206, `POST`→201 + `Location`, `PUT`/`PATCH`→200, `DELETE`→204; `4xx` client / `5xx` server with the problem+json body.
   - `PUT`/`DELETE`/`GET` idempotent; `POST` not. Safe methods have no side effects.
   - Content negotiation via `Accept`/`Content-Type`; no bespoke status codes.
3. **Lint the spec** — copy `templates/api/.spectral.yaml` → `api/.spectral.yaml` (oas + custom rules: no-verbs-in-paths, versioned paths, problem+json errors, operationId, pagination) and run `spectral lint api/openapi.yaml --ruleset api/.spectral.yaml`. Must pass before any codegen.
4. **Generate FROM the spec** (framework-specific):
   - `fastapi` → Pydantic models + routers from schemas (datamodel-code-generator); handlers stubbed, not invented.
   - `express`/`spring`/other → openapi-generator server stub + typed client.
5. **Contract test** — the implementation is verified against the spec (Python: Schemathesis; else Dredd). Copy `templates/ci/api-contract.yml` → the repo's CI dir; it runs Spectral lint + Schemathesis against the running app (catching undocumented routes = the real spec-first enforcement). Add `api-contract` to branch-protection `required_checks` only if the team wants the contract enforced at merge.
6. **Wire cross-cutting**: error-envelope handler, `auth-gen` security middleware for protected ops, `observability-gen` per-route structured logging + latency/error metrics.

## Output / validation
- `api/openapi.yaml` (source of truth) + `api/.spectral.yaml` + generated stubs/client + contract tests.
- Validation: `spectral lint api/openapi.yaml` passes; contract tests green against the running app.
- Print a coverage note: which spec operations have handlers vs are still stubbed.

## Refuses when
- No `framework` declared in `org-profile.yaml` (codegen target unknown).
- `framework` is `streamlit` or `none` — no HTTP API surface (Streamlit is a UI runtime; use `frontend-gen`).
- Asked to write endpoint code that has no corresponding spec operation (spec-first is the rule — add it to the spec first).
- GraphQL/gRPC requested (out of scope).
