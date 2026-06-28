---
name: caching
description: Use when adding a cache layer — pick the pattern (cache-aside/read-through), design keys + TTL, and wire the invalidation, stampede protection, and stale-data safeguards a naive cache omits. Triggers — "add caching", "cache this query/response", "Redis cache", "reduce DB/LLM load", "cache invalidation", "why is cached data stale". NOT for runtime feature flags (feature-flags), NOT for the vector store (retriever), NOT for a CDN/edge cache, NOT for a messaging idempotency-key store (event-driven). Reads org-profile.yaml `platform`/`framework`; refuses on mismatch.
---

# Caching — the defenses a naive cache forgets

This skill is advisory — it designs the cache (pattern, key/TTL scheme, invalidation, stampede defense) and wires the client. It does NOT guarantee correctness: a cache is a **consistency hazard**, and the only real enforcement is the VERIFY checks + the invalidation path you commit and test. The core rule: **a cache must never become a hard dependency or a silent source of stale truth** — every entry has a documented TTL *and* an invalidation strategy, the read path is protected against stampede, and a cache outage fails open to the source.

## When to use
- "add a cache in front of this query/endpoint", "cache this response"
- "reduce DB/LLM load with caching", "set up Redis caching"
- "fix stale cached data" / "design cache invalidation"
- A read-heavy hot path where recomputing/refetching is expensive and bounded staleness is acceptable

## When NOT to use
- Runtime feature flags / config that flips at runtime → `feature-flags` (a config store with a different consistency model, not a TTL cache)
- Vector / embedding / semantic store → `retriever` (similarity search, not key→value caching)
- CDN / static-asset / edge caching → out of scope (different layer; say so and stop)
- An idempotency-key / dedup store for messaging → `event-driven` (owns consumer dedup; this is not a message cache)

## Inputs
- `org-profile.yaml` → `platform` and `framework` — REQUIRED. `platform` picks the backing store + auth wiring (Azure → Azure Cache for Redis via managed identity); `framework` picks the client integration (fastapi → async client + dependency; streamlit → cached resource). Refuse on mismatch/unset.
- What is being cached + its **staleness tolerance**: read/write ratio, cardinality, and the consistency requirement (how stale is acceptable — this sets the TTL).
- `stack-interface.yaml` (OPTIONAL) → resolve the Redis endpoint/auth through the `stack-adapter` agent, never a literal key.

## Steps
1. **Read `org-profile.yaml`; resolve `platform`/`framework`.** If unset or not the supported (Azure + Python FastAPI/Streamlit) shape, REFUSE — do not hardcode a store.
2. **Pick the pattern.** Default to **cache-aside** (app reads cache, on miss loads source then populates) — explicit, easy to reason about. Use **read-through** only behind a caching client that owns load. Reject **write-through / write-back** unless write amplification or write-latency hiding is explicitly justified (write-back risks data loss on crash — call it out).
3. **Key design.** Namespaced, versioned keys: `app:<entity>:v<schema>:<id>` (or a stable hash of the query + args). The `v<schema>` segment lets a deploy bust an entire class of entries by bumping the version. Never key on unbounded/user-controlled input without hashing + a length bound.
4. **TTL from staleness tolerance.** Choose the TTL from the stated tolerance and **write it down** — there is no untimed entry. Short TTL for volatile data, longer for stable; no entry without an expiry (an entry with no TTL and no eviction is a leak).
5. **Invalidation — required.** Every cached class declares HOW it is busted: write-driven (delete/overwrite the key on the source mutation) or event-driven (subscribe to the change and bust). A cache with a TTL but no invalidation strategy is a stale-data bug — REFUSE to ship it. TTL is a backstop, not the invalidation plan.
6. **Stampede protection.** Prevent the thundering herd when a hot key expires: **single-flight / lock-on-miss** (one caller recomputes, the rest await the result) and/or **jittered TTL** (randomize expiry ±N% so keys don't expire in lockstep). State which you used.
7. **Safeguards.** Negative-result caching with a SHORT bounded TTL (cache "not found" to stop hammering the source, but briefly); a max cached payload size (don't cache megabyte blobs); and **graceful degradation** — on cache error/timeout, log + fall through to the source (fail open), never propagate the cache failure to the caller.
8. **Backing store + auth.** Azure Cache for Redis, accessed via **managed identity** (`DefaultAzureCredential`) or a **Key Vault secret reference** — never a literal connection string/key in code or config (route auth to the `secrets` skill; if `stack-interface.yaml` exists, get the endpoint/auth from `stack-adapter`, `MISSING-MAPPING` → standard SDK against the endpoint, note no wrapper). Set an `maxmemory-policy` eviction (e.g. `allkeys-lru`).
9. **Observability.** Emit hit ratio, miss count, eviction count, and key-load latency via `observability-gen`; alert on a collapsing hit ratio or rising evictions (both signal a mis-sized cache or a key explosion).

## Output / validation
- A cache design + client wiring: chosen pattern, the key scheme (namespaced + versioned), per-class TTL + invalidation strategy, stampede defense, the fail-open degradation path, and managed-identity/KV-ref Redis auth — plus the hit-ratio/eviction metrics.
- Validation: warm the cache, mutate the source, and confirm the invalidation path serves fresh data (not the stale TTL value); kill the cache and confirm reads still succeed against the source (fail open); confirm no literal Redis connection string/key is present (hard fail). Managed-identity / KV-ref wiring is the recommended auth and an *advisory* VERIFY note — not a gate, since auth may legitimately resolve through `stack-adapter`/env without an explicit `DefaultAzureCredential` token.
- Boundary: this skill designs and wires the cache; it does not enforce correctness. The teeth are the committed invalidation path + the VERIFY functional check + the hit-ratio alert. The VERIFY blocking greps are scoped to the cache module and co-located with a cache-client call (a bare `.set(` with no `ex=`/`px=`, a missing cache-client `delete`, etc. fail); they are a backstop, not a proof of correctness — the functional check is.

## Refuses when
- `org-profile.yaml` missing, or `platform`/`framework` not the supported (Azure + Python FastAPI/Streamlit) stack.
- A cache is requested with no stated invalidation strategy AND no acceptable staleness window — refuse; an un-invalidatable cache over mutable data is a stale-data bug.
- Redis access would use a literal connection string/key instead of managed identity / a Key Vault reference.
- Asked to cache something that must be strongly consistent / read-your-own-writes on every read (a cache cannot promise that — say so and stop).
