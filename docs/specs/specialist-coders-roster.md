# Spec — Specialist coder roster (Pass 2)

Status: Draft (scope for the SECOND refonte pass, after the usability pass lands)
Requirement: R5 (expanded). The base specialists (security / DB / API / monitoring / auth) are only a seed. The user wants a specialist **coder agent** for **every element that composes application code** — quality over quantity, each one ultra-precise and "peaufiné PARFAITEMENT pour répondre au cahier des charges à 100%". Each specialist works in **application-code mode first** (zero cloud tool), with an **optional Azure specialization layer** on top.

## Principle: coder AGENT vs advisory SKILL
- Today Fenrir has ~47 **skills** (procedures/knowledge) and a handful of generic **agents** (architect/coder/qa/reviewer/red-team). Most domain skills are *advisory* — they tell you how, they don't autonomously write the diff.
- R5 wants **autonomous coder sub-agents**: the main thread (deliver) **auto-routes** a scoped change to the *right* specialist coder, which writes the minimal correct diff **in its own context** (keeps the main thread lean — R2), then hands back a terse receipt.
- Rule of thumb: a concern becomes a **coder agent** when it (a) writes/edits code, (b) has a deep, stable "cahier des charges" (a checklist of what "done right" means in that domain), and (c) is invoked often enough to amortize a dedicated agent. Otherwise it stays a **skill** (knowledge the generic coder loads).

## The roster (every code element)
Legend: **[NEW]** to build · **[MAP]** wrap/upgrade an existing skill into a coder agent · **[KEEP]** already covered.

### A. Structure & contracts
- **api-coder** — HTTP endpoints, routing, request/response, status codes, pagination, OpenAPI contract. [MAP api-first]
- **schema-coder** — data models / DTOs / validation / (de)serialization (pydantic). The `schemas/` layer. [NEW]
- **domain-services-coder** — business logic / use-cases / the `services/` layer; pure, testable, no I/O leakage. [NEW]
- **data-access-coder** — repositories, ORM models, queries, transactions, N+1 elimination, indexes-from-access-patterns. [MAP data-model + db-migration]

### B. Cross-cutting concerns
- **auth-coder** — authn/authz, sessions, tokens/JWT, RBAC, route guards, middleware. [MAP auth-gen]
- **security-coder** — input sanitization, secret handling, injection/XSS/CSRF/SSRF defense, safe crypto usage, authz checks at the boundary. [MAP security-review → coder]
- **config-coder** — settings/env management, the `core/` layer, typed config, validation-on-boot, feature flags. [NEW] (+ feature-flags skill)
- **resilience-coder** — error handling, retries, timeouts, backpressure, circuit breakers, graceful degradation, idempotency. [NEW]
- **caching-coder** — cache-aside/read-through, keys/TTL, invalidation, stampede protection. [MAP caching]
- **observability-coder** — structured logging, metrics, tracing, correlation IDs, log hygiene (no secrets). [MAP observability-gen]

### C. Async & integration
- **concurrency-coder** — async/await correctness, threading, locks, race/deadlock avoidance, cancellation. [NEW]
- **messaging-coder** — producers/consumers, queue/topic, dead-letter, ordering, exactly/at-least-once. [MAP event-driven]
- **jobs-coder** — background workers, schedulers, cron, idempotent periodic tasks. [MAP cronjob]
- **integration-coder** — third-party API clients, SDK wrappers, webhooks, rate-limit/retry handling. [NEW]

### D. Data & storage
- **migration-coder** — safe, reversible, lock-free schema migrations, backfills, tested up→down→up. [KEEP db-migration]
- **storage-coder** — file uploads, blob/object storage, streaming, large-file handling. [NEW]
- **search-coder** — full-text + vector search, hybrid, recall@k. [MAP retriever]

### E. Interface
- **frontend-coder** — components, state, accessibility, framework conventions. [MAP frontend-gen]
- **realtime-coder** — websockets, SSE, streaming transports, reconnection/backpressure. [MAP realtime-transport]
- **cli-coder** — command-line interfaces, argument parsing, exit codes, UX. [NEW]

### F. Quality & lifecycle
- **testing-coder** — unit/integration/e2e, fixtures, mocks, property-based, coverage-of-behavior. [KEEP qa-tester]
- **performance-coder** — measure-first optimization under one stated constraint. [KEEP optimize]
- **refactor-coder** — structure-preserving cleanup under a green-test guard. [KEEP refactor/simplify]
- **docs-coder** — docstrings, API docs, READMEs, changelog kept in sync with the diff. [KEEP doc-keeper]

### G. AI / LLM (when the app is LLM-shaped)
- **llm-coder** — typed provider wrapper, prompt management, token/cost tracking, golden-set eval. [KEEP llm-gen]
- **rag-coder** — chunking, embeddings, retrieval, KB freshness/citation. [MAP retriever + knowledge-base]
- **agent-workflow-coder** — LangGraph/state machines, tools, checkpoints, human-in-the-loop. [KEEP langgraph-workflow]

## Layering: core app-code first, Azure optional
- Every specialist ships a **core** behaviour that works on plain application code with **zero** az/terraform/gh/kubectl.
- Cloud specialization is a **separate optional layer** the specialist consults only when the repo opts in (org-profile `platform`/`cloud_layer: azure`). E.g. `observability-coder` (core: OTel + structured logs) → Azure layer (App Insights wiring); `auth-coder` (core: OIDC middleware) → Azure layer (Entra). The Azure layer NEVER loads or blocks for a local user.

## Auto-routing (R2)
- `deliver` gains a **router**: classify the scoped change → dispatch to the single best specialist coder (not the generic coder), which works in its own context and returns a terse receipt. Generic `coder` becomes the fallback only.
- The router is deterministic where possible (path/glob + change-kind), model-judged only when ambiguous, and is the mechanism that stops main-thread pollution: specialists churn in isolated contexts.

## Build plan (Pass 2)
1. For each **[NEW]/[MAP]** specialist: write its "cahier des charges" checklist (what done-right means), its trigger + NOT-for boundaries, its core behaviour, and its optional Azure layer.
2. Build them as agents (`agents/<name>.md`) with sharp tool scopes; MAP ones reuse the existing skill body as the knowledge base.
3. Add the deliver **router** + make specialists auto-delegated.
4. Validate each against a representative task ("does it solve the real problem clearly and completely?") with a qa + red-team gate — same discipline as the usability pass.

> Quality bar: a specialist ships only when it resolves its concern **cleanly and completely** on a representative task — adversarially verified. No half-built specialists.
