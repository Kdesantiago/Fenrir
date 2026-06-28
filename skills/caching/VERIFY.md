# VERIFY — caching

Run after `caching` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] every cached entry sets a TTL (no untimed `set` on the cache path): `grep -rEq '\b(set|setex|set_ex|expire|ttl|ex=|px=)\b' . && echo OK || echo MISSING`
- [ ] an invalidation strategy exists — keys are busted on source mutation, not just left to expire: `grep -rEq '\b(delete|invalidate|bust|evict|del\()' . && echo OK || echo MISSING`
- [ ] stampede protection is wired (single-flight / lock-on-miss OR jittered TTL): `grep -rEq 'single.?flight|lock|jitter|random.*ttl|setnx|nx=' . && echo OK || echo MISSING`
- [ ] the read path fails OPEN to the source on cache error (cache outage is not a hard dependency): `grep -rEq 'except|try:|fallback|fail.?open|on error|degrade' . && echo OK || echo MISSING`
- [ ] Redis auth is managed identity / Key Vault ref — NO literal connection string or key: `! grep -rEq 'redis://[^@]*:[^@]+@|password=|accesskey|AccountKey=|[A-Za-z0-9+/]{40}=' . && grep -rEq 'DefaultAzureCredential|ManagedIdentity|KeyVault|@Microsoft.KeyVault' . && echo OK || echo SECRET-OR-CONNSTR-FOUND`
- [ ] keys are namespaced + schema-versioned (a deploy can bust a whole class): `grep -rEq '[a-z]+:[a-z]+:v[0-9]|namespace|key_prefix|:v\{' . && echo OK || echo MISSING`
- [ ] (profile-driven) `platform`/`framework` in `org-profile.yaml` is the supported (Azure + Python FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `python -c 'import redis'` (or `redis.asyncio`) · `command -v redis-cli` · `command -v az` (`az redis` extension) → note absent, don't fail
- [ ] a hit-ratio / eviction metric is exported via `observability-gen` (cache health is observable)

## Functional
Warm the cache for a hot key, then mutate the source and confirm the invalidation path serves the FRESH value (not the stale TTL'd one); fire many concurrent misses on one expired key and confirm only a single source load happens (stampede protection holds); finally, take the cache offline and confirm reads still succeed by falling through to the source (fail open) — none of the three should surface a cache error to the caller.
