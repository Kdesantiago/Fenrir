# VERIFY — resilience

Run after `resilience` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **hardened call site(s)** — the file(s) wrapping a boundary-crossing call (HTTP/DB/queue/cache) with resilience logic — not the whole repo. A repo-wide search is not falsifiable (a stray `timeout=`, a lone `try:`, or a `for` loop would pass with zero resilience code). Resolve the call-site file(s) first, then run the co-located checks against them:

```
RES_FILES=$(grep -rlE 'httpx\.|aiohttp|requests\.|\.(get|post|put|delete|patch)\(|tenacity|retry|circuit.?breaker|CircuitBreaker|backoff' --include='*.py' . )
echo "${RES_FILES:-<none — no hardened call site found, FAIL>}"
```
If `RES_FILES` is empty, the skill produced no wired call site → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **timeout on every outbound call** — no unbounded wait. Fail when a client call in the file has no timeout/deadline: `for f in $RES_FILES; do grep -nqE 'timeout=|Timeout\(|deadline|connect_timeout|read_timeout|\.settimeout' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-TIMEOUT`
- [ ] **bounded retry with backoff + jitter** — retries are capped and spaced, not a tight infinite loop: `for f in $RES_FILES; do grep -qE 'max_attempts|stop_after_attempt|max_retries|retries\s*=|attempt\s*<' "$f" && grep -qE 'backoff|wait_exponential|jitter|random\.|expo|sleep\(' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-BOUNDED-BACKOFF`
- [ ] **transient-only retry** — retries are gated on a retryable-error predicate, not blanket `except Exception: retry`: `for f in $RES_FILES; do grep -qE 'retry_if|TimeoutError|ConnectionError|status_code\s*(>=|in)|5[0-9]{2}|transient|is_retryable' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-TRANSIENT-GATE`
- [ ] **idempotency guard on retried writes** — a state-changing retried op carries a dedup key / upsert (skip-OK only if the file has no write call): `for f in $RES_FILES; do grep -qE 'idempotency|Idempotency-Key|dedup|upsert|on_conflict|merge\(|if_not_exists' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NOTE-no-idempotency-key-confirm-reads-only`
- [ ] **graceful degradation** co-located — exhausted/hung dependency yields a fallback or trips a breaker, not a cascade: `for f in $RES_FILES; do grep -qE 'circuit.?breaker|CircuitBreaker|fallback|degrade|bulkhead|Semaphore|fail.?open|return .*(cached|default|partial)' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-DEGRADATION`
- [ ] **errors mapped, not swallowed / not leaked** — caught and re-raised as a domain/problem+json error, no bare `except: pass` and no raw stack to the client: `for f in $RES_FILES; do grep -qE 'except\s+\(?(Exception|BaseException)\)?\s*:\s*(pass|\.\.\.)\s*$' "$f" && echo "SWALLOW in $f"; done; [ -z "$(for f in $RES_FILES; do grep -E 'except\s+\(?(Exception|BaseException)\)?\s*:\s*(pass|\.\.\.)\s*$' "$f"; done)" ] && echo OK || echo SILENT-SWALLOW`
- [ ] (profile-driven) `framework` in `org-profile.yaml` is the supported (Python FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] **resilience library present** — advisory, NOT a gate (hand-rolled timeout/retry is valid): `python -c 'import tenacity' 2>/dev/null && echo "tenacity present" || echo "NOTE: no tenacity — confirm hand-rolled retry/backoff is bounded"`; also note `import pybreaker`/`circuitbreaker` if a breaker was wired
- [ ] retry/timeout/breaker-state signals are emitted via `observability-gen` (failure behavior is observable)
- [ ] SDK-level retry config (Azure SDK `retry_total`/`retry_backoff`, ENV-driven) noted where an Azure client is used — no code-level cloud dependency required

## Functional
Stub the downstream and exercise the four failure modes against the hardened call site: (1) make it hang → the call TIMES OUT within the bound, it does not block forever; (2) make it fail transiently N−1 times then recover → the bounded retries succeed and total retry time stays under the deadline; (3) fire the same state-changing call twice → exactly one effect lands (idempotent); (4) keep it down past the attempt cap → the caller gets a mapped degraded response (fallback / clear error) and, where wired, the circuit breaker trips OPEN — never a cascade, never a raw stack trace surfaced to the client.
