# VERIFY — integration-client

Run after `integration-client` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **outbound-client / webhook module(s)** — the file(s) wrapping a third-party API call or handling a webhook — not the whole repo. A repo-wide search is not falsifiable (a stray `timeout=`, a lone `requests.get`, or a `for` loop would pass with zero integration code). Resolve the client file(s) first, then run the co-located checks against them:

```
INT_FILES=$(grep -rlE 'httpx\.|aiohttp|requests\.|\.(get|post|put|delete|patch)\(|base_url|Authorization|webhook|X-.*Signature|Retry-After|paginat|next_cursor|rel=.?next' --include='*.py' . )
echo "${INT_FILES:-<none — no client/webhook module found, FAIL>}"
```
If `INT_FILES` is empty, the skill produced no wired client → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **typed response mapping** — vendor JSON is parsed into a model, not passed up as a raw dict: `for f in $INT_FILES; do grep -qE 'BaseModel|model_validate|parse_obj|TypeAdapter|\.model_validate_json|: .*Model' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-TYPED-MAPPING`
- [ ] **timeout on every outbound call** — no unbounded wait to a third party: `for f in $INT_FILES; do grep -nqE 'timeout=|Timeout\(|connect_timeout|read_timeout' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-TIMEOUT`
- [ ] **pagination walked to exhaustion** — follows next/cursor/Link, not a single page (skip-OK only if the API is single-shot): `for f in $INT_FILES; do grep -qE 'next_cursor|next_page|has_more|rel=.?next|while .*next|continuation|page\s*\+?=|offset' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NOTE-no-pagination-confirm-single-shot`
- [ ] **rate-limit honored** — 429 / Retry-After is respected, not tight-looped: `for f in $INT_FILES; do grep -qE 'Retry-After|429|X-RateLimit|rate.?limit|too_many_requests' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-RATE-LIMIT-HONOR`
- [ ] **webhook signature verified before side effect** — inbound webhook is authenticated (skip-OK only if no inbound webhook handler): `for f in $INT_FILES; do grep -qE 'hmac|compare_digest|verify.*sign|X-.*Signature|constant_time|svix|webhook_secret' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NOTE-no-webhook-verify-confirm-no-inbound-hook`
- [ ] **no literal vendor secret** — auth key resolved via secrets/env/KV-ref, not hardcoded: `for f in $INT_FILES; do grep -nqE '(api[_-]?key|secret|token|bearer)\s*=\s*["'\''][A-Za-z0-9_\-]{16,}["'\'']' "$f" && echo "LITERAL in $f"; done; [ -z "$(for f in $INT_FILES; do grep -nE '(api[_-]?key|secret|token|bearer)\s*=\s*["'\''][A-Za-z0-9_\-]{16,}["'\'']' "$f"; done)" ] && echo OK || echo HARDCODED-SECRET`
- [ ] (profile-driven) `framework` in `org-profile.yaml` is the supported (Python FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] **resilience composed, not re-rolled** — retry/backoff delegated to `resilience` (advisory; hand-rolled bounded retry is valid): `for f in $INT_FILES; do grep -qE 'tenacity|from .*resilience|retry_if|wait_exponential' "$f" && echo "resilience wired $f"; done | grep -q wired && echo "OK" || echo "NOTE: confirm retry/backoff is bounded"`
- [ ] call-count / latency / 429-rate signals emitted via `observability-gen` (integration health is observable)
- [ ] SDK-level config (vendor SDK retry/timeout via ENV/constructor) noted where a vendor SDK is used — no code-level cloud dependency required

## Functional
Stub the third-party provider and exercise the four integration modes against the wired client: (1) return TWO pages → both are walked and merged, no page silently dropped; (2) return `429` + `Retry-After: N` → the client backs off ~N before retrying, it does not hammer; (3) POST an inbound webhook with a BAD signature → it is rejected (4xx) BEFORE any side effect lands, and a replayed valid event is deduped to one effect; (4) return a vendor 5xx / malformed body → the caller gets a mapped domain error, never the vendor's raw stack/body, and no literal API key appears in the diff.
