---
name: integration-client
description: >-
  Use when consuming a THIRD-PARTY API or SDK from this repo — wrap the outbound
  client (auth headers, base URL, typed response mapping), walk pagination to
  exhaustion, honor the provider's rate limit (429 + Retry-After), and handle
  webhooks in and out (signature verify on receipt, signed delivery on send).
  Triggers — "call the Stripe/GitHub/Twilio API", "wrap this vendor SDK",
  "handle their pagination / rate limit", "receive/verify a webhook", "map the
  JSON response to a typed model". NOT for YOUR OWN HTTP endpoints (→ api-first),
  NOT for queues / pub-sub messaging (→ event-driven), NOT for the generic
  retry/timeout/breaker policy (→ resilience — this skill composes it).
  Refuses-when — org-profile mismatch | design→architect | gate/merge→reviewer |
  gate-file touches. Reads org-profile.yaml `framework`; refuses off-stack.
tools: Read, Grep, Glob, Edit, Write, Bash
model: inherit
---

# Integration-client — the outbound client a naive `requests.get` forgets

This skill is advisory — it wraps a third-party API/SDK with the integration concerns naive code omits: typed auth, pagination-to-exhaustion, rate-limit honor, response→model mapping, and webhook verify (in + out). It does NOT guarantee correctness: the teeth are the VERIFY checks + the qa-tester/red-team gate. The core rule: **no vendor response is trusted raw, no page is silently dropped, no 429 is hammered, and no webhook is processed without a verified signature.**

## When to use
- "call this third-party API / wrap this vendor SDK", "add a client for <provider>"
- "walk their pagination", "handle their rate limit / 429 / Retry-After"
- "receive and verify an inbound webhook", "send a signed outbound webhook"
- Any outbound call to an API this repo does not own, mapped to a typed model

## When NOT to use
- YOUR OWN HTTP endpoints / the contract you publish → `api-first` (you own that surface)
- Queue / topic / pub-sub / dead-letter messaging → `event-driven` (not request/response HTTP)
- The generic timeout / retry / backoff / circuit-breaker policy → `resilience` (this skill *composes* it, never re-implements)
- Secret/credential storage for the vendor key → `secrets`; DESIGNING the system → `architect`; gating/merging → `reviewer`

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED for the client shape (fastapi → async httpx client + dependency; streamlit → sync). Refuse off-stack/unset.
- The provider contract: base URL, auth scheme (bearer/API-key/OAuth2 header), pagination style (cursor/offset/`Link` header), rate-limit signal (429 + `Retry-After`/`X-RateLimit-*`), and the webhook signature scheme (HMAC header).
- Resilience helpers from `resilience` + secret resolution from `secrets` — REUSE, do not duplicate.
- Core is ZERO cloud (no az/terraform/kubectl/gh). Optional Azure layer — opt in only via org-profile `cloud_layer: azure` (e.g. APIM egress / Event Grid webhook delivery); never required, never loads for a local user.

## Steps
1. **Read `org-profile.yaml`; resolve `framework`.** Off-stack/unset → REFUSE; do not hardcode a client.
2. **One typed client per provider.** Single base-URL client, auth header injected from a resolved secret (never a literal key), explicit `Accept`/version header, and a connect+read timeout on every call (compose `resilience`, don't re-roll).
3. **Map responses to typed models.** Parse the JSON into a pydantic model at the boundary — never pass a raw `dict` upward. Reject/log unexpected shapes; tolerate unknown fields, fail on missing required ones.
4. **Paginate to exhaustion.** Follow the cursor / `Link: rel=next` / offset until the provider says stop — never assume one page. Bound total pages/items so a runaway feed can't loop forever; yield lazily.
5. **Honor the rate limit.** On 429 (or a depleting `X-RateLimit-Remaining`) back off for `Retry-After` before retrying — never tight-loop a throttled endpoint. Stay under the documented budget; this is transient-retry territory, delegate the mechanism to `resilience`.
6. **Inbound webhooks: verify first.** Verify the signature (HMAC/`X-*-Signature`) and reject on mismatch BEFORE any side effect; enforce a timestamp/nonce window against replay; dedup by event id (delivery is at-least-once). Return 2xx fast, process async.
7. **Outbound webhooks: sign + make deliverable.** Sign the payload (HMAC over the raw body), send with a timeout + bounded retry, and treat the receiver as at-least-once (the consumer dedups). Log delivery outcome.
8. **Map errors at the boundary.** Translate vendor 4xx/5xx and transport failures to a domain error — never leak the vendor's raw body/stack to your caller; emit call-count/latency/429 signals via `observability-gen`.

## Output / validation
- A typed outbound client: secret-resolved auth header, per-call timeout, response→pydantic mapping, pagination-to-exhaustion with a bound, 429/`Retry-After` honor, and webhook verify (in) + sign (out) — plus call/latency/rate-limit signals.
- Validation: stub the provider to return two pages → confirm both are walked (no silent drop); to return 429 + `Retry-After` → confirm it backs off, not hammers; post an inbound webhook with a bad signature → confirm it is rejected before any side effect, and a replayed one is deduped; confirm no literal API key is present (hard fail).
- Boundary: this skill wires the integration; it does not enforce correctness. The teeth are the committed verify/pagination/rate-limit path + the VERIFY checks + the qa-tester/red-team gate. VERIFY greps are scoped to the touched client/webhook module (a bare vendor call with no timeout, an unverified webhook handler) — a backstop, not a proof; the functional check is.

## Refuses when
- `org-profile.yaml` missing, or `framework` not the supported (Python FastAPI/Streamlit) stack.
- Asked to process an inbound webhook WITHOUT verifying its signature — refuse; an unauthenticated webhook is an injection vector. Verify first or stop.
- Asked to embed a literal vendor API key/secret instead of resolving it via `secrets` / a Key Vault reference.
- Asked to build YOUR OWN endpoint contract (→ `api-first`), a queue consumer (→ `event-driven`), to DESIGN the architecture (→ `architect`), to gate/merge (→ `reviewer`), or to touch a gate file (`.claude/`, CI).
