---
name: event-driven
description: Use when building a message-driven integration — a producer/consumer over a queue/topic/event stream with the reliability an HTTP call lacks. Triggers — "publish/consume a message", "queue", "pub/sub", "Service Bus / Event Grid / Event Hubs", "dead-letter / poison". NOT for scheduled jobs (cronjob), NOT for sync HTTP (api-first), NOT for provisioning the bus (iac-gen). Picks the primitive from the contract (ordering/throughput/fan-out), not compute stack; reads org-profile.yaml `framework` for the client, checks `platform` is Azure; refuses without both.
---

# Event-Driven — delivery discipline over a bus

Putting a message on a bus is the easy 5%. The skill's job is the other 95%: pick the right Azure messaging primitive and apply the delivery discipline a naive producer/consumer omits so the integration doesn't **drop messages**, **process duplicates**, or **redeliver a poison message forever**. The skill advises and scaffolds; the real gate is couche-0 (CI required-checks + branch-protection) plus the DLQ-depth/consumer-lag alerts wired through `observability-gen` — a skill cannot make at-least-once delivery safe by itself.

## When to use
- "publish an event / consume from a queue or topic", "set up pub/sub between services"
- "handle dead-letter / poison messages", "fan out a webhook to multiple consumers"
- Wiring a producer or consumer over Service Bus / Event Grid / Event Hubs with retry, dedup, and DLQ

## When NOT to use
- Time-triggered recurring run (nightly/hourly/cron expression) → `cronjob`
- In-process / request-deferred async work on one service (no bus involved) → out of scope (this skill is for a producer/consumer over a real bus)
- Synchronous request/response HTTP contract → `api-first`
- Provisioning the bus/namespace/topic infra itself → `iac-gen` (file emitter)
- The TTL / eviction / stampede *mechanics* of the backing dedup store → `caching` (this skill owns the dedup **key + lookup-on-consume**; `caching` owns the store's TTL/stampede behavior)

## Inputs
- The **delivery contract** (REQUIRED — this drives the primitive): ordering needed? duplicates tolerable? expected throughput / fan-out count. If this is unspecified, REFUSE — the primitive is unknowable without it.
- The **message/event contract**: schema + version, and direction (produce / consume)
- `org-profile.yaml` → `framework` (REQUIRED — selects the emitted producer/consumer client + SDK: `fastapi`/`express`/`spring`/`streamlit`; `none` = no app code to emit). Refuse if unset.
- `org-profile.yaml` → `platform` — used only to confirm this is an Azure stack (`aks`/`webapp`/`k8s`/`serverless`/`vm`). REFUSE `ecs` (AWS — wrong cloud for the Azure primitives below). `platform` does NOT pick the primitive.
- `stack-interface.yaml` (if present) → bus endpoint/auth + deploy via the `stack-adapter` wrappers, never a literal connection string

## Steps
1. **Resolve the delivery contract, `framework`, and `platform`.** REFUSE if the delivery contract (ordering / duplicate tolerance / throughput / fan-out) is unspecified — the primitive is chosen from it, not from any profile key. Read `org-profile.yaml`: REFUSE if `framework` is unset (the emitted client language is unknowable); confirm `platform` is an Azure stack (`aks`/`webapp`/`k8s`/`serverless`/`vm`) and REFUSE `ecs` (AWS — these Azure primitives don't apply). Cross-ref `iac-gen` if the namespace/topic does not yet exist — this skill writes the producer/consumer, not the infra.
2. **Pick the primitive from the delivery contract (justify the choice):**
   - **Service Bus** → commands / work queues; ordering via **sessions**, FIFO, transactions, scheduled messages, native per-message DLQ. The default for "do this work exactly once-ish".
   - **Event Grid** → reactive **discrete events** (resource changed, webhook fan-out); push delivery, many subscribers, built-in retry + dead-letter to storage.
   - **Event Hubs** → high-throughput **streams / telemetry**; partitioned, consumer-group offsets, replay. Not a work queue.
   - State the read/write/ordering/throughput reason; do not default to Service Bus reflexively.
3. **Define the contract** — a **versioned** message/event schema wrapped in a **CloudEvents 1.0** envelope (`id`, `source`, `type`, `specversion`, `subject`, `time`, `datacontenttype`, `data`). A schema change is a contract change: add a new `type`/version, never silently mutate the old shape. Validate payloads against the schema on both produce and consume.
4. **Consumer idempotency (mandatory — this skill owns it).** At-least-once is the delivery reality on every Azure bus — duplicates WILL arrive (redelivery, retry, at-least-once semantics). This skill OWNS the dedup **key** (message `id` / an explicit **idempotency key**) and the **lookup-on-consume + early-return-on-hit** logic in the consumer. The backing store's TTL / eviction / stampede mechanics are owned by `caching` — do not design those here; just consume the store (or use the Service Bus duplicate-detection window where it fits). State the dedup key + the lookup/early-return strategy, or REFUSE: a non-idempotent consumer over at-least-once delivery corrupts state.
5. **Reliability defaults (this is the point):**
   - **Bounded retry + backoff** on transient failures — exponential with jitter, a finite max attempt count, never infinite in-line retry.
   - **Dead-letter path**: route exhausted/invalid messages to the **DLQ** (Service Bus native `$DeadLetterQueue`; Event Grid dead-letter to a storage account; Event Hubs → an explicit error stream/store). Capture the dead-letter reason + correlation id.
   - **Poison-message handler**: distinguish a *poison* message (will never succeed — bad schema, validation failure) from a *transient* failure (retry). Poison goes straight to DLQ; do not redeliver it into an infinite loop.
   - **DLQ replay**: a documented, manual or gated path to inspect and re-submit DLQ messages after the defect is fixed.
6. **Auth via managed identity.** Connect with `DefaultAzureCredential` (managed identity / workload identity), bound to a `Fully Qualified Namespace`. NEVER a literal connection string or SAS key in code/env — route secret references through the `secrets` skill (Key Vault ref). A literal connection string is a defect.
7. **Observability + alerting** (via `observability-gen` / `obs_backend`): propagate a **trace correlation id** through the envelope; emit publish / consume / retry / **DLQ-depth** / **consumer-lag** metrics. Alert on **DLQ growth** and **consumer lag** — a consumer that silently stops or a DLQ that silently fills is the failure mode that goes unnoticed.
8. **Deploy / wire endpoints.** If `stack-interface.yaml` exists, resolve the bus endpoint/login and any deploy op through `stack-adapter` **only for ops it has a wrapper for**. If the needed wrapper key is blank/absent, `stack-adapter` returns `MISSING-MAPPING` — do NOT stall: emit the standard form (managed-identity client against the FQDN) and note that no enterprise wrapper was declared for this op.

## Output / validation
- The producer and/or consumer code **in the language/SDK of the declared `framework`** (`fastapi` → Python + `azure-servicebus`/`azure-eventgrid`/`azure-eventhub`; `express` → Node + `@azure/service-bus` etc.; `spring` → Java + Spring Cloud Stream / `azure-messaging-*`; `streamlit` → Python; `none` → no app code, contract + runbook only) — never hardcode Python on a non-Python stack. Each carries: versioned schema + CloudEvents envelope, idempotent handler (dedup key + lookup/early-return), bounded retry, DLQ + poison-message path, managed-identity client. Plus a short runbook: which primitive and why, the contract version, the idempotency strategy, the DLQ/replay procedure, and where the DLQ/lag alert fires.
- Validation: schema is versioned and validated both sides; consumer dedup proven (a replayed duplicate is a no-op); a forced poison message lands in the DLQ (not an infinite loop); auth is managed identity with no literal connection string; DLQ-depth + consumer-lag alerts wired.
- These checks become teeth only once committed and run by CI (couche-0) + the live alerts — not by this skill.

## Refuses when
- The **delivery contract** (ordering / duplicate tolerance / throughput / fan-out) is unspecified — the primitive is chosen from it and is unknowable without it.
- `framework` is unset in `org-profile.yaml` (the emitted producer/consumer language/SDK is unknowable).
- `platform` is `ecs` (AWS) or any non-Azure stack — the Service Bus / Event Grid / Event Hubs primitives do not apply; route to the appropriate cloud's tooling.
- The consumer mutates state but no idempotency / dedup strategy is given — REFUSE (a non-idempotent consumer over at-least-once delivery corrupts data).
- No dead-letter / poison-message path is defined (unbounded redelivery is not acceptable).
- Asked to authenticate with a literal connection string or SAS key inline — REFUSE; route to the `secrets` skill for a Key Vault / managed-identity reference.
- The request is a scheduled/recurring job (`cronjob`) or synchronous HTTP (`api-first`) — out of scope; route to the named sibling. In-process deferred work with no bus is also out of scope (no bus, no event-driven delivery discipline to apply).
