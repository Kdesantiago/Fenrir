---
name: concurrency
description: >-
  Use when code runs work concurrently — async/await over an event loop, threads,
  locks, or bounded parallelism — and must stay correct under interleaving: every
  await/lock has a timeout, shared state is guarded, tasks are cancellable and
  cancellation-safe, and parallelism is bounded. Triggers — "make this async /
  correct under load", "add a lock", "fix this race / deadlock", "cancel this
  task", "run these in parallel / gather", "why does this hang / interleave
  wrong". NOT for failure/retry policy on one outbound call (resilience), NOT for
  messaging/queues/dead-letter (event-driven), NOT for scheduled/periodic jobs
  (cronjob), NOT for defining the OTel metric (observability-gen). Refuses-when:
  org-profile framework off-stack | design/ADR → architect | gate/merge →
  reviewer | gate-file (.claude/, CI) touches. Reads org-profile.yaml `framework`.
  Core is ZERO cloud; an optional Azure layer is opt-in via org-profile
  `cloud_layer`, never required.
tools: Read, Grep, Glob, Edit, Write, Bash
model: inherit
---

# Concurrency — the correctness a happy-path interleaving forgets

This skill is advisory — it makes concurrent code correct under interleaving: no unbounded wait, no unguarded shared state, no leaked/uncancellable task, no unbounded fan-out. It does NOT guarantee correctness: the teeth are the VERIFY checks + the qa-tester/red-team gate. The core rule: **never block the loop, never touch shared state without a guard, never spawn a task you can't cancel, and never fan out without a bound.**

## When to use
- "make this async / correct under load", "run these in parallel / gather"
- "add a lock", "fix this race / deadlock", "this hangs / interleaves wrong"
- "cancel this task / shut down cleanly", "bound the concurrency"
- Any code with shared mutable state, an event loop, threads, or concurrent fan-out

## When NOT to use
- Failure/retry/timeout on ONE outbound call → `resilience` (it owns backoff+idempotency; concurrency owns the *interleaving*)
- The messaging primitive / queue / dead-letter / ordering → `event-driven`; scheduled/periodic work → `cronjob`
- Defining the OTel metric or dashboard → `observability-gen` (concurrency *emits* contention/queue-depth signals)
- DESIGNING the system / an ADR → `architect`; gating or merging → `reviewer`

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED for the model (fastapi → asyncio over the loop; streamlit → threads/sync). Refuse off-stack/unset.
- The work + its shared state: which data is mutated by >1 task, the cancellation/shutdown points, and the acceptable parallelism bound (pool size / semaphore).
- Existing async helpers (timeout/backpressure) from `observability-gen`/`resilience` — REUSE, do not duplicate.

## Steps
1. **Read `org-profile.yaml`; resolve `framework`.** Off-stack/unset → REFUSE; do not assume a model.
2. **Never block the loop.** No sync I/O, no `time.sleep`, no CPU-bound work inline in async code — offload to a thread/process pool (`run_in_executor` / `asyncio.to_thread`). A blocking call on the loop stalls every coroutine.
3. **Bound every wait.** Wrap awaits and lock acquisitions in `asyncio.timeout`/`wait_for` (or lock-acquire timeouts) — an unbounded await is a silent hang. Acquire multiple locks in a **fixed global order** to kill lock-ordering deadlock.
4. **Guard shared state.** Mutable state touched by >1 task gets a `Lock`/`Semaphore` (or is made immutable / message-passed). Hold the lock for the *whole* read-modify-write — a check-then-act outside it is the race.
5. **Bound the parallelism.** Fan-out goes through a `Semaphore` / bounded pool / queue with backpressure — never an unbounded `gather` over an unbounded input (it exhausts connections/memory). Cap it and document the cap.
6. **Make tasks cancellable + cancellation-safe.** Track spawned tasks (prefer `TaskGroup` / structured concurrency so a child failure cancels siblings and nothing leaks); on cancel, `CancelledError` propagates (never swallow it), and cleanup runs in `finally`. No fire-and-forget task without a reference.
7. **Emit the signals.** Surface queue depth, active-task count, lock-wait time, and cancellation count via `observability-gen` (this skill emits; that skill defines the alert).

## Output / validation
- Concurrency-correct code: no loop-blocking call, every await/lock bounded by a timeout, shared state guarded for the full RMW, fan-out behind a semaphore/bounded pool, tasks tracked + cancellation-safe (`finally` cleanup, no swallowed `CancelledError`) — plus the contention/queue-depth signals.
- Validation: run the hot path under concurrent load and assert no corrupted shared state (race-free); stub a slow dependency → confirm the bounded await times out, not hangs; cancel mid-flight → confirm cleanup ran and no task leaked; fan out over a large input → confirm the semaphore caps in-flight work.
- Boundary: this skill wires the interleaving correctness; it does not enforce it. The teeth are the committed guard/timeout/bound + the VERIFY checks + the qa-tester/red-team gate. VERIFY greps are scoped to the touched concurrent module (a bare `gather` with no bound, a `sleep` on the loop, an unguarded shared mutation) — a backstop, not a proof; the functional check is.

## Optional Azure layer
Core is **ZERO cloud** (no az/terraform/kubectl/gh) — pure language/runtime concurrency. ONLY when `org-profile.yaml` opts in via `cloud_layer` may a distributed-lock note (e.g. a blob-lease / Redis lock for cross-instance mutual exclusion) be added — opt-in, never required, and routed through the relevant cloud skill.

## Refuses when
- `org-profile.yaml` missing, or `framework` not the supported (Python FastAPI/Streamlit) stack.
- Asked to add a blocking/sync call onto the event loop, or an unbounded `gather` over unbounded input — refuse; that stalls the loop or exhausts the pool. Offload / bound first.
- Asked to swallow `CancelledError` or fire-and-forget an untracked task — refuse; that defeats cancellation and leaks work.
- Asked to DESIGN the architecture (→ `architect`), to gate/merge (→ `reviewer`), or to touch a gate file (`.claude/`, CI).
