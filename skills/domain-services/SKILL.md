---
name: domain-services
description: >-
  Use-when implement a business use-case / domain rule in the `services/` layer —
  "the service that does X", "orchestrate this workflow", "enforce this business
  rule". Path — `src/<module>/services/`. NOT-for HTTP shape/status → use api-coder;
  persistence/queries/migrations → use data-access-coder; request/response DTO
  validation → use schema-coder; retry/timeout/circuit-breaker → use
  resilience-coder. Refuses-when asked to put framework objects (Request/Response) or
  raw I/O in the use-case | asked to design the architecture (→ architect) | asked to
  gate/merge (→ reviewer) | touches a gate file (.claude/, CI).
---

# Domain-services — business logic that never touches a framework

This skill implements the `services/` layer: **pure-ish use-cases** that hold the business rules, framework-free and I/O-free, so they are deterministic and unit-testable. The core rule: **the use-case is the one place an invariant lives, and it reaches the outside world only through injected ports** — never an inline DB/HTTP/queue call, never a `Request`/`Response`, never an ORM row handed straight out. It is **cloud-agnostic by design**: it runs with no `az`/`terraform`/`gh` present.

## When to use
- "implement the use-case / business rule", "the service that does X"
- "orchestrate this workflow across repositories/clients"
- "enforce this invariant in one place"
- A handler is fat with logic that belongs below the transport layer

## When NOT to use
- HTTP method/status/contract → `api-coder` (the handler adapts to this service, not vice-versa)
- ORM models / queries / N+1 / migrations → `data-access-coder` (it implements the ports this layer declares)
- Request/response DTO validation + serialization → `schema-coder`
- Timeout / retry / backoff / idempotency / circuit-breaker → `resilience-coder` (it wraps the port calls)

## Inputs
- The use-case to implement + its **business invariants** (the rules that must always hold) and its domain error cases.
- The collaborators it needs (repository / client / clock / id-gen) — these become **port interfaces** (`Protocol`/ABC), injected, never instantiated inline.
- The domain/schema types for inputs and outputs (from `schema-coder`); never an ORM row as the boundary type.

## Steps
1. **Name the use-case + its invariants.** One function or class per use-case; write down the business rules it enforces before any code.
2. **Declare ports, don't reach for I/O.** Every DB/HTTP/queue/clock/id dependency is a typed `Protocol`/ABC parameter (constructor or function arg). No inline `session.execute`, `httpx.get`, `os.environ`, `datetime.now()` — inject a clock/port instead. No framework imports.
3. **Boundary types are domain/schema, not ORM.** Accept domain types or schema models; return domain results. An ORM row never leaves this layer.
4. **Enforce invariants HERE, with explicit domain errors.** Raise typed domain errors (`InsufficientFunds`, `AlreadyExists`) — not HTTP status codes, not bare `Exception`. api-coder maps them to problem+json; resilience-coder maps transient ones.
5. **No hidden state.** No module-level singletons, no global mutation; every side-effecting collaborator is a parameter, so the function is deterministic given its inputs + injected ports.
6. **Make it trivially mockable.** Dependencies are mockable by construction (fakes/stubs satisfy the Protocol) — the use-case must be unit-testable with **no** DB or network.

## Output / validation
- Use-case(s) in `services/`: the port interfaces they require, the business invariants enforced with explicit domain errors, domain-typed in/out — and zero framework/I-O leakage. data-access-coder implements the ports; api-coder adapts to HTTP.
- Validation: import and exercise a use-case in a unit test with **fake ports only** (no DB/network) and assert behavior + each domain-error path; grep the `services/` module for framework imports (`fastapi`, `starlette`, `Request`), raw I/O (`httpx`, `requests`, a DB session), and `datetime.now()`/`os.environ` — all should be absent.
- Boundary: this skill owns the use-case purity, not the transport or persistence. The teeth are the VERIFY greps (no framework/I-O in `services/`) + a unit test that runs with no infrastructure.

## Refuses when
- Asked to put a `Request`/`Response`/framework object, or an inline DB/HTTP/queue call, inside a use-case — that defeats the layer; route transport to api-coder and persistence to data-access-coder.
- Asked to hand an ORM row out as the service's return type (leaks persistence into the domain).
- Asked to encode HTTP status codes or retry/timeout policy in the service (→ api-coder / resilience-coder).
- Asked to design the module architecture rather than implement a scoped use-case (→ architect).

## Cloud layer
- None required — this layer is cloud-agnostic by design and works with no `az`/`terraform`/`gh`. (Opt-in only: if org-profile sets `cloud_layer: azure`, a cloud-backed port *implementation* is data-access-coder's lane, never inlined here.)
