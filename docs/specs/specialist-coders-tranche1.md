# Spec — Specialist coders, Tranche 1 (structural core + universal cross-cutting)

Status: Draft (build-ready). Parent: `docs/specs/specialist-coders-roster.md` (the full 26).
Scope: tranche-1 only — the specialists that map 1:1 onto the pass-1 init layout
`src/<module>/{core,api,services,schemas}` (ADR `docs/adr/0005-init-module-layout.md`, FLAT,
module-local imports `from core.settings import settings`) plus the cross-cutting concerns that
apply to **almost every** app. Tranche-2 (the remainder) is a one-line backlog at the bottom.

## Why these ten (and not more) in tranche-1

The init layout scaffolds four layers per module. Tranche-1 must field a specialist that *owns*
each of those layers, plus the cross-cutting concerns no app escapes. Mapping:

| init layer / concern | tranche-1 specialist | real recurring problem it solves |
|---|---|---|
| `core/` (settings.py) | **config-coder** | env/config sprawl, untyped settings, no fail-fast on boot |
| `api/` (routes.py) | **api-coder** | ad-hoc routes, no contract, drift between spec and handler |
| `services/` | **domain-services-coder** | business logic tangled with I/O, untestable use-cases |
| `schemas/` | **schema-coder** | unvalidated input, leaky/over-exposing DTOs, serialization bugs |
| (cuts across, persistence) | **data-access-coder** | N+1, missing indexes, unsafe/unreviewed migrations |
| authn/authz | **auth-coder** | hand-rolled tokens, unguarded routes, broken session wiring |
| boundary safety | **security-coder** | injection/XSS/SSRF, secret leakage, missing authz at the edge |
| logs/metrics/traces | **observability-coder** | print-debugging, no correlation IDs, secrets in logs |
| failure behavior | **resilience-coder** | no timeout/retry, cascading failure, non-idempotent retries |
| behavior proof | **testing-coder** | unverified diffs — the MANDATORY gate (KEEP qa-tester) |

Every row is a problem that recurs in essentially every service, so each amortizes a dedicated
agent (roster rule of thumb §9). No filler: messaging/jobs/storage/search/frontend/realtime/cli and
the LLM family are genuinely concern-specific and **not** universal — they go to tranche-2.

**Confirmed set (no drops, no adds).** The proposed ten are exactly the structural core + the
four most-universal cross-cutting concerns + the gate. The one judgment call — whether
`resilience-coder` belongs in tranche-1 vs tranche-2 — resolves to **tranche-1**: timeout/retry/
idempotency is a property every network-touching handler needs from the first endpoint, and the
init scaffold already has a `GET /health` handler that crosses a process boundary the moment it
does real work. It stays.

---

## Cahiers des charges (per specialist)

Each block: **tag** · **trigger** · **NOT-for** · **cahier (100%-done checklist)** · **core
app-code behavior** · **Azure layer (optional, one line)**. Builders turn each block directly into
`agents/<name>.md` with the sharp tool scope noted; MAP/KEEP specialists load the named skill body
as their knowledge base instead of re-deriving it.

---

### 1. config-coder — the `core/` layer  ·  [NEW]

- **Trigger:** "add a setting / env var", "type the config", "read this from .env", "validate config
  on boot", "wire a feature flag". Path: `src/<module>/core/{settings,config}.py`.
- **NOT for:** secret *storage*/rotation (→ `secrets`/Key Vault), business logic (→ domain-services),
  the runtime flag *store/targeting* mechanism (→ feature-flags skill for App Config); config-coder
  only declares and reads the flag.
- **Cahier (done-right = 100%):**
  1. One typed settings object — `pydantic-settings BaseSettings`, `env_prefix="<MODULE>_"`, reads
     `.env` (matches ADR-0005). No scattered `os.getenv` calls anywhere else in the module.
  2. Every field typed + defaulted-or-required; required fields with **no** default so a missing one
     fails **at import/boot**, not at first use. Validators for constrained values (URLs, enums,
     ranges, ports).
  3. Secrets read from ENV/config, **never** literal in source; `.env.example` documents every var
     (prefix-correct) and is kept in sync with the model.
  4. Settings are a singleton imported as `from core.settings import settings`; no re-instantiation,
     no import-time network/DB calls.
  5. Feature flags declared with a typed default + a clear "where the value comes from" note; off by
     default; safe to remove.
- **Core behavior:** author/extend `core/settings.py` + `.env.example`; convert stray `getenv` into
  typed fields; add boot-time validation.
- **Azure layer:** when `cloud_layer: azure`, source flags/values from **Azure App Configuration**
  (feature-management lib) with ENV-driven endpoint — never hardcoded.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 2. api-coder — the `api/` layer  ·  [MAP api-first]

- **Reuses:** `skills/api-first/SKILL.md` (load as knowledge base — OpenAPI 3.1, RFC 9457 problem+json,
  REST review, Spectral, contract tests).
- **Trigger:** "add a REST endpoint", "design this API", "fix the status code / pagination", "wire the
  router". Path: `src/<module>/api/routes.py`, `api/openapi.yaml`.
- **NOT for:** consuming a 3rd-party API (→ integration-coder, tranche-2), GraphQL/gRPC (out of scope),
  business logic inside the handler (→ domain-services), DTO shapes (→ schema-coder).
- **Cahier (done-right = 100%):**
  1. **Spec first** — operation exists in `api/openapi.yaml` before its handler; handler matches it.
  2. REST correctness (block on violation): plural-noun resources, no verbs in paths, correct verb→
     status (`POST`→201+`Location`, `DELETE`→204, …), idempotent `GET/PUT/DELETE`.
  3. One error envelope everywhere — `application/problem+json` (RFC 9457).
  4. `/v1` path prefix; breaking change → `/v2`, never mutate `/v1`.
  5. List endpoints carry the consistent pagination/sort/filter contract; `Idempotency-Key` on
     retryable POSTs.
  6. Handler is **thin**: validate (schema-coder model) → call a service (domain-services) → map result
     to response. No business logic, no raw SQL in the route.
  7. Protected operations carry the `securityScheme`; auth enforcement delegated to auth-coder
     middleware, not re-implemented inline.
- **Core behavior:** extend `openapi.yaml`, generate/stub the FastAPI router, wire the problem+json
  handler, call into services. Spectral lint must pass.
- **Azure layer:** none required at code level (transport/ingress is iac-gen's concern).
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 3. domain-services-coder — the `services/` layer  ·  [NEW]

- **Trigger:** "implement the use-case / business rule", "the service that does X", "orchestrate this
  workflow". Path: `src/<module>/services/`.
- **NOT for:** HTTP shape/status (→ api-coder), persistence/queries (→ data-access-coder), DTO
  validation (→ schema-coder), retry/timeout policy (→ resilience-coder).
- **Cahier (done-right = 100%):**
  1. Pure-ish use-case functions/classes: **no framework objects** (no `Request`/`Response`), **no raw
     I/O leakage** — DB/HTTP/queue access goes through injected ports (repository/client interfaces),
     not inline.
  2. Inputs/outputs are domain types or schema models, never ORM rows handed straight out.
  3. Business invariants enforced **here** (the one place), with explicit domain errors — not HTTP
     status codes, not bare exceptions.
  4. Deterministic and unit-testable **without** a DB/network (dependencies mockable by construction).
  5. No hidden global state; side-effecting collaborators are parameters.
- **Core behavior:** write the use-case in `services/`, define the port interfaces it needs, return
  domain results; let api-coder adapt to HTTP and data-access-coder implement the ports.
- **Azure layer:** none — this layer is cloud-agnostic by design (that is the point).
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 4. schema-coder — the `schemas/` layer  ·  [NEW]

- **Trigger:** "add a request/response model", "validate this input", "the DTO for X", "fix the
  serialization". Path: `src/<module>/schemas/`.
- **NOT for:** the ORM/persistence model (→ data-access-coder), the OpenAPI path/operation (→ api-coder
  owns the contract; schema-coder owns the `components/schemas` shapes feeding it), business rules
  (→ domain-services).
- **Cahier (done-right = 100%):**
  1. Pydantic v2 models; every field typed with explicit constraints (lengths, ranges, regex, enums) —
     validation is **declarative on the model**, not scattered `if` checks.
  2. **Separate** in/out models: request DTOs never accept server-controlled fields (id, timestamps,
     role); response DTOs never expose internal/secret fields (password hashes, internal flags) —
     no over-posting, no over-exposure.
  3. Strict parsing: unknown fields rejected (`extra="forbid"`) on inputs where appropriate; coercion
     rules explicit.
  4. Round-trip safe: serializes/deserializes losslessly; field aliases handled; `datetime`/`Decimal`/
     enum encode deterministically.
  5. No business logic and no I/O in validators (only shape/constraint checks).
- **Core behavior:** author the pydantic in/out models, validators, and serializers in `schemas/`;
  these are the types api-coder binds and domain-services consumes.
- **Azure layer:** none.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 5. data-access-coder — repositories, ORM, queries, migrations  ·  [MAP data-model + db-migration]

- **Reuses:** `skills/data-model/SKILL.md` (schema/index/N+1/EXPLAIN) **and** `skills/db-migration/SKILL.md`
  (safe reversible Alembic). Loads both as knowledge base.
- **Trigger:** "model these entities", "this query is slow / fix the N+1", "add an index", "alter a
  column / write the migration", "implement the repository". Path: ORM models, repository impls,
  `alembic/versions/`.
- **NOT for:** HTTP layer (→ api-coder), in/out DTOs (→ schema-coder), vector/embedding search
  (→ search-coder, tranche-2), business logic (→ domain-services — data-access implements its ports).
- **Cahier (done-right = 100%):**
  1. Normalized schema (3NF default); explicit relationships with `back_populates` + ON DELETE;
     denormalize only with a stated read/write justification.
  2. **Every index names the query it serves** (composite most-selective-first; covering/partial where
     it pays). No index that is pure write-cost.
  3. N+1 eliminated by an explicit loading strategy (`selectinload`/`joinedload`, `lazy="raise"` on hot
     paths); before/after query count shown.
  4. Keyset pagination backed by the `(sort_key, id)` index matching the cursor api-coder defines.
  5. Hot paths proven with `EXPLAIN ANALYZE` — index used, no surprise seq-scan.
  6. Migrations: autogenerate **then human-review**, real reversible `downgrade()`, lock-light DDL
     (`CREATE INDEX CONCURRENTLY` in its own non-transactional migration), backfill split from schema
     change, idempotent, tested **up→down→up** on a throwaway DB; destructive change requires an
     expand→migrate→contract plan.
  7. Repositories expose the domain-services ports; no ORM rows leak past this layer.
- **Core behavior:** implement repositories + ORM models, design indexes from access patterns, write
  the reviewed Alembic revisions. (CI/deploy applies migrations — not this agent.)
- **Azure layer:** when `platform` Azure DB, note connection/identity via Managed Identity + ENV; no
  hardcoded connection strings.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 6. auth-coder — authn/authz, sessions, tokens, route guards  ·  [MAP auth-gen]

- **Reuses:** `skills/auth-gen/SKILL.md` (OIDC/OAuth2 middleware glue for the declared provider).
- **Trigger:** "wire up OIDC/login", "validate the JWT", "protect these endpoints", "add RBAC / a route
  guard", "session wiring". Provider from `org-profile.yaml auth_provider`.
- **NOT for:** end-user SSO product features (account-linking UI, tenant admin), input sanitization /
  injection defense (→ security-coder), the secret store (→ secrets/Key Vault).
- **Cahier (done-right = 100%):**
  1. Use the provider's **vetted library** (entra/okta/keycloak/auth0) — never hand-roll token/crypto.
  2. Full OIDC flow wired: login redirect → callback → token/JWT **validation** (signature, `iss`,
     `aud`, `exp`, nonce/state) → session.
  3. Authz enforced at the route boundary via middleware/dependency (RBAC/scopes), applied to **every**
     protected operation api-coder marks — fail-closed (deny by default).
  4. All issuer/client/secret config from ENV/config; nothing literal in source.
  5. Output flagged **requires human review** before merge; never auto-injected into protected paths
     unreviewed.
- **Core behavior:** generate the OIDC middleware + token-validation + route guards bound to the
  declared provider; expose the dependency api-coder attaches to protected routes.
- **Azure layer:** provider `entra` → Microsoft Entra ID app-registration wiring (issuer/JWKS via ENV).
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 7. security-coder — boundary safety  ·  [MAP security-review → coder]

- **Reuses:** `skills/security-review/SKILL.md` (SAST + threat-check vocabulary: injection, authz gaps,
  unsafe deserialization, SSRF, path traversal) — but acts as a **coder** that writes the fix, not only
  the report.
- **Trigger:** "sanitize this input", "fix the injection/XSS/SSRF", "this handles untrusted data", "add
  the authz check at the boundary", "safe crypto usage". Runs on diffs touching input handling,
  deserialization, file paths, outbound URLs, crypto.
- **NOT for:** OIDC/session/token plumbing (→ auth-coder), secret scanning (→ gitleaks pre-commit hook),
  lint/type/test (→ delivery-gates).
- **Cahier (done-right = 100%):**
  1. Untrusted input is validated/parameterized at the boundary — parameterized queries (no string-SQL),
     output-encoding for XSS, allowlist for SSRF-prone outbound URLs, path-normalization against
     traversal.
  2. No unsafe deserialization (`pickle`/`yaml.load`/eval on untrusted bytes); safe loaders only.
  3. Crypto uses vetted primitives (no homemade ciphers, no static IV, no MD5/SHA1 for security); secrets
     never logged or echoed.
  4. **Authz check present at the boundary** for every state-changing/object-scoped operation (no IDOR);
     deny-by-default.
  5. Each fix maps to a file:line and the threat class it closes; re-running security-review on the diff
     reproduces clean.
- **Core behavior:** write the sanitization/parameterization/authz-guard diff on the flagged paths;
  fold security-review findings into concrete code changes.
- **Azure layer:** none at code level (secret backing is `secrets`/Key Vault's lane).
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 8. observability-coder — logs, metrics, traces, correlation  ·  [MAP observability-gen]

- **Reuses:** `skills/observability-gen/SKILL.md` (vendor-neutral OTel init, semantic conventions, SLI/SLO
  + alert rules).
- **Trigger:** "add structured logging", "instrument with OpenTelemetry", "add a metric / trace span",
  "correlation IDs", "define the SLO". `obs_backend` from profile.
- **NOT for:** business logic, alert *delivery*/routing to a channel (→ alert-delivery), LLM tracing
  specifics beyond OTel wiring (→ llm-gen/online-llm-eval).
- **Cahier (done-right = 100%):**
  1. **Structured** logs (JSON, leveled) — no `print`, no f-string-into-stdout; one logger config per
     module.
  2. **No secrets/PII in logs** — redaction at the boundary; log hygiene is non-negotiable.
  3. Correlation/request ID propagated through the request lifecycle and present on every log line +
     span.
  4. OTel SDK init via the framework provider; spans/metrics follow **semantic conventions**; exporter
     wired strictly via ENV/config (OTLP endpoint/headers) — backend **never hardcoded** (switching
     backend = ENV change, no code edit).
  5. The golden signals are instrumented (latency, error rate, throughput, saturation) so SLIs/alerts
     have data; SLO targets + alert rules authored where asked.
- **Core behavior:** add the OTel init + structured-logger + correlation-ID middleware + per-route
  latency/error metrics; author SLI/SLO/alert rules for the declared backend.
- **Azure layer:** `obs_backend: azure-monitor` → App Insights/Azure Monitor exporter via ENV
  (connection string from config), Azure Monitor alert rules.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 9. resilience-coder — error handling, retries, timeouts, idempotency  ·  [NEW]

- **Trigger:** "add a timeout/retry", "make this resilient / fail gracefully", "circuit breaker",
  "make this retry-safe / idempotent", "handle the downstream being down". Runs on any handler/service
  that crosses a process boundary (DB, HTTP, queue, cache).
- **NOT for:** the messaging primitive itself / dead-letter semantics (→ messaging-coder, tranche-2),
  OTel metrics (→ observability-coder — resilience emits the signals, doesn't define the dashboard),
  caching stampede (→ caching-coder, tranche-2).
- **Cahier (done-right = 100%):**
  1. **Every outbound call has a timeout** — no unbounded waits; connect + read timeouts both set.
  2. Retries only on **transient** failures, with exponential backoff + jitter and a **bounded** attempt
     count; never retry a non-idempotent op without an idempotency key.
  3. Idempotency: state-changing operations that may be retried are made idempotent (idempotency key /
     dedup / upsert), so a retry can't double-apply.
  4. Failures degrade **gracefully** — fallback/partial response/clear error, not a cascade; a circuit
     breaker (or bulkhead/bounded concurrency) protects against a hung dependency where the call volume
     warrants it.
  5. Errors are caught at the right layer, mapped to domain errors (domain-services) or problem+json
     (api-coder) — never swallowed silently, never leaked as a raw stack trace to the client.
- **Core behavior:** wrap outbound calls with timeout+retry+backoff, add idempotency keys/guards,
  introduce circuit-breaker/bounded-concurrency where load warrants, and route errors to the right
  envelope. (Pairs with observability-coder's async patterns — reuse, don't duplicate, its
  timeout/retry/backpressure helpers.)
- **Azure layer:** none at code level (SDK-level retry config still applies, ENV-driven).
- **Tools:** Read, Grep, Glob, Edit, Write, Bash.

---

### 10. testing-coder — the validation gate  ·  [KEEP qa-tester]

- **Reuses:** existing `agents/qa-tester.md` — **no new agent file**. Tranche-1 work = **register it in
  the deliver router** as the mandatory post-build gate for every specialist route (it already is the
  delivery gate; the router must dispatch to it, not bypass it).
- **Trigger:** end of **every** specialist route (after the coder returns its diff). Also: "write the
  tests for X", "add coverage", "is this actually tested".
- **NOT for:** writing the feature code (that's the specialist above it), red-team/abuse testing
  (→ red-team-destroyer, the paired adversarial gate), perf load profiles (→ load-test).
- **Cahier (done-right = 100%):**
  1. Tests assert **behavior**, not implementation — the contract/use-case, the error paths, the edge
     cases — not line coverage for its own sake.
  2. Each layer tested at the right level: schema (validation/round-trip), services (pure unit, mocked
     ports), api (contract/integration via TestClient), data-access (query + migration up→down→up).
  3. Fixtures/mocks isolate the unit; no hidden reliance on a live network/DB in unit tests.
  4. Negative + boundary cases present (bad input, authz-denied, downstream-down/timeout, retry-dedup).
  5. The suite actually runs green in the module's own venv (`cd src/<module> && uv run pytest`) per
     ADR-0005.
- **Core behavior:** author/extend the test suite for the just-built diff and run it; report pass/fail
  honestly. Paired with red-team-destroyer for the adversarial half of the gate.
- **Azure layer:** none.
- **Tools:** (inherits qa-tester's existing scope.)

---

## Router registration (tranche-1 deliverable, shared)

The deliver **router** dispatches a scoped change to exactly one tranche-1 specialist, deterministic
where possible. Suggested first-pass dispatch (path/glob + change-kind; model-judged only on tie):

| signal | → specialist |
|---|---|
| `core/settings.py`, `.env*`, "config/env/flag" | config-coder |
| `api/`, `openapi.yaml`, "endpoint/route/REST" | api-coder |
| `services/`, "use-case/business rule" | domain-services-coder |
| `schemas/`, "DTO/validate/model (request/response)" | schema-coder |
| ORM/repo/`alembic/`, "query/index/N+1/migration" | data-access-coder |
| "auth/login/OIDC/JWT/guard/RBAC" | auth-coder |
| diff touches input/deserialize/path/URL/crypto, "sanitize/injection/SSRF" | security-coder |
| "log/metric/trace/correlation/SLO" | observability-coder |
| "timeout/retry/idempotent/circuit-breaker/graceful" | resilience-coder |
| (always, post-build) | testing-coder + red-team-destroyer gate |

Generic `coder` is the fallback only. All specialists run in their own context and return a terse
receipt (keeps the main thread lean — R2). Every route ends in the testing-coder gate; no specialist
self-approves.

---

## Tranche-2 backlog (one line each — NOT in scope here)

- **caching-coder** [MAP caching] — cache-aside/TTL/invalidation/stampede.
- **concurrency-coder** [NEW] — async correctness, locks, race/deadlock, cancellation.
- **messaging-coder** [MAP event-driven] — producer/consumer, dead-letter, ordering, delivery semantics.
- **jobs-coder** [MAP cronjob] — schedulers, idempotent periodic tasks.
- **integration-coder** [NEW] — 3rd-party clients, webhooks, rate-limit/retry.
- **storage-coder** [NEW] — file uploads, blob/object storage, streaming large files.
- **search-coder** [MAP retriever] — full-text + vector/hybrid search, recall@k.
- **frontend-coder** [MAP frontend-gen] — components, state, a11y, framework conventions.
- **realtime-coder** [MAP realtime-transport] — websockets/SSE, reconnection/backpressure.
- **cli-coder** [NEW] — argument parsing, exit codes, CLI UX.
- **performance-coder** [KEEP optimize] — measure-first optimization under one constraint.
- **refactor-coder** [KEEP refactor/simplify] — structure-preserving cleanup under green tests.
- **docs-coder** [KEEP doc-keeper] — docstrings/API-docs/README/changelog in sync with the diff.
- **llm-coder** [KEEP llm-gen] — typed provider wrapper, prompts, token/cost, golden-set eval.
- **rag-coder** [MAP retriever + knowledge-base] — chunking/embeddings/retrieval, KB freshness/citation.
- **agent-workflow-coder** [KEEP langgraph-workflow] — graph/state machine, tools, checkpoints, HITL.
