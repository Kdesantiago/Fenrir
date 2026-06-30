---
name: resilience
description: >-
  Use when making a call that crosses a process boundary survive failure — bound
  every outbound call with a timeout, retry only transient errors with
  backoff+jitter under a capped attempt count, make retried state-changes
  idempotent, degrade gracefully (fallback/circuit-breaker), and map errors to the
  right envelope. Triggers — "add a timeout/retry", "make this resilient / fail
  gracefully", "circuit breaker", "make this retry-safe / idempotent", "handle the
  downstream being down". NOT for the messaging primitive / dead-letter semantics
  (event-driven), NOT for defining the OTel metric/dashboard (observability-gen —
  resilience emits the signals), NOT for cache stampede (caching). Reads
  org-profile.yaml `framework`; refuses off-stack.
---

# Resilience — the failure behavior a happy-path call forgets

This skill is advisory — it wraps boundary-crossing calls (DB, HTTP, queue, cache) with the failure defenses naive code omits: timeout, bounded retry+backoff+jitter, idempotency, graceful degradation, circuit breaker. It does NOT guarantee correctness: the teeth are the VERIFY checks + the qa-tester/red-team gate. The core rule: **no outbound call waits forever, no retry double-applies, and a hung dependency degrades — never cascades.**

## When to use
- "add a timeout/retry to this call", "make this resilient / fail gracefully"
- "circuit breaker", "make this retry-safe / idempotent"
- "handle the downstream being down" without taking the whole service with it
- Any handler/service that crosses a process boundary (DB, HTTP, queue, cache)

## When NOT to use
- The messaging primitive itself / dead-letter / poison-queue semantics → `event-driven`
- Defining the OTel metric, SLO, or dashboard → `observability-gen` (resilience *emits* the retry/timeout signals; it does not own the dashboard)
- Cache stampede / single-flight on a hot key → `caching` (it owns the cache-miss thundering-herd)
- DESIGNING the system / an ADR → `architect`; gating or merging → `reviewer`

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED for the client integration (fastapi → async client + dependency; streamlit → sync). Refuse off-stack/unset.
- The call to harden + its failure profile: which errors are **transient** (retryable) vs terminal, whether the op is **idempotent**, and the acceptable degraded response.
- Existing async resilience helpers from `observability-gen` (timeout/retry/backpressure) — REUSE, do not duplicate.

## Steps
1. **Read `org-profile.yaml`; resolve `framework`.** Off-stack/unset → REFUSE; do not hardcode a client.
2. **Timeout every outbound call.** Set BOTH connect and read timeouts — no unbounded wait. An untimed call is the bug this skill exists to kill.
3. **Retry only transient failures.** Classify errors first; retry 5xx/timeouts/connection-resets, never 4xx/validation. Exponential **backoff + jitter**, a **bounded** attempt cap, and a deadline so total retry time stays bounded.
4. **Idempotency before retry on writes.** A state-changing op that may be retried gets an idempotency key / dedup / upsert so a retry cannot double-apply. Never retry a non-idempotent write without one.
5. **Degrade gracefully.** On exhausted retries: fallback / cached / partial response / a clear mapped error — never a cascade. Add a **circuit breaker** (or bulkhead / bounded concurrency) where call volume warrants, so a hung dependency trips open instead of exhausting the pool.
6. **Map errors at the right layer.** Catch at the boundary, translate to a domain error (services) or problem+json (api) — never swallow silently, never leak a raw stack trace to the client.
7. **Emit the signals.** Surface retry count, timeout count, and breaker state/transitions via `observability-gen` (this skill emits; that skill defines the alert).

## Output / validation
- A hardened call site: timeout (connect+read), transient-only retry with backoff+jitter+cap, idempotency guard on retried writes, a graceful-degradation path (fallback / breaker), and errors mapped to the right envelope — plus the retry/timeout/breaker signals.
- Validation: stub the downstream to hang → confirm the call times out (not hangs); to fail transiently then recover → confirm bounded retries succeed; to fire the same write twice → confirm one effect (idempotent); to stay down → confirm a mapped degraded response, not a cascade, and the breaker trips.
- Boundary: this skill wires the failure behavior; it does not enforce correctness. The teeth are the committed timeout+idempotency path + the VERIFY checks + the qa-tester/red-team gate. VERIFY greps are scoped to the touched call site (a bare client call with no timeout, an unbounded retry) — a backstop, not a proof; the functional check is.

## Refuses when
- `org-profile.yaml` missing, or `framework` not the supported (Python FastAPI/Streamlit) stack.
- Asked to add retries to a non-idempotent state-changing op with no idempotency key — refuse; a blind retry there double-applies. Add the key first or stop.
- Asked to retry on terminal/validation (4xx) errors — refuse; that hammers a request that will never succeed.
- Asked to DESIGN the architecture (→ `architect`), to gate/merge (→ `reviewer`), or to touch a gate file (`.claude/`, CI).
