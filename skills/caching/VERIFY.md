# VERIFY — caching

Run after `caching` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **cache module** — the file(s) that wire the Redis/cache client — not the whole repo. A repo-wide word search is not falsifiable (a stray `db.delete(x)`, a `"ttl"` string, or any `try:` would pass with zero caching code). Resolve the cache file(s) first, then run the co-located checks against them:

```
CACHE_FILES=$(grep -rlE 'redis\.(asyncio\.)?(Redis|from_url|StrictRedis)|aioredis|get_redis|cache_client|RedisCluster|ConnectionPool' --include='*.py' . )
echo "${CACHE_FILES:-<none — cache module not found, FAIL>}"
```
If `CACHE_FILES` is empty, the skill produced no wired cache client → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **TTL on every set** — no untimed write on the cache client. Fail when a `.set(` call in the cache file has no `ex=`/`px=` expiry (a bare `redis.set(k, v)` is the leak this skill blocks; `setex`/`set_ex` carry their own expiry and pass): `for f in $CACHE_FILES; do grep -nE '\.set\(' "$f" | grep -vE 'ex=|px=|setex|set_ex' && echo "UNTIMED-SET in $f" ; done; [ -z "$(for f in $CACHE_FILES; do grep -E '\.set\(' "$f" | grep -vE 'ex=|px=|setex|set_ex'; done)" && echo OK || echo MISSING-TTL`
- [ ] **invalidation is wired to a cache call** — keys are busted on source mutation, not just left to expire. The bust token must co-locate with a cache-client `delete`/`unlink` in the cache file (not any ORM/dict delete elsewhere): `for f in $CACHE_FILES; do grep -qE '\.(delete|unlink)\(|invalidate|bust' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING`
- [ ] **stampede protection** co-located in the cache file (single-flight / lock-on-miss OR jittered TTL): `for f in $CACHE_FILES; do grep -qE 'single.?flight|Lock\(|lock_on_miss|jitter|random\.[a-z]+\([^)]*ttl|setnx|nx=True' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING`
- [ ] **read path fails OPEN** — a cache error/timeout in the cache file falls through to the source, not propagated to the caller: `for f in $CACHE_FILES; do grep -qE 'except\s+\(?(redis|Redis|ConnectionError|TimeoutError)|fail.?open|fallback|fall.?through' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING`
- [ ] **no literal connection string / key** anywhere (hard fail): `! grep -rEq 'redis://[^@[:space:]]*:[^@[:space:]]+@|rediss://[^@[:space:]]*:[^@[:space:]]+@|AccountKey=|password\s*=\s*["'\''][^"'\''$@{]|accesskey\s*=' . && echo OK || echo CONNSTR-OR-KEY-FOUND`
- [ ] **keys are namespaced + schema-versioned** in the cache file (a deploy can bust a whole class): `for f in $CACHE_FILES; do grep -qE '[a-z_]+:[a-z_]+:v[0-9]|key_prefix|namespace|:v\{|:v\$\{' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING`
- [ ] (profile-driven) `platform`/`framework` in `org-profile.yaml` is the supported (Azure + Python FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] **managed-identity / KV-ref auth note** — advisory, NOT a gate. Legitimate wiring may resolve auth purely through `stack-adapter`/env with none of these literal tokens present, so absence does not fail: `grep -rEq 'DefaultAzureCredential|ManagedIdentity|WorkloadIdentity|@Microsoft.KeyVault|stack-adapter' . && echo "managed-identity wiring present" || echo "NOTE: no explicit DefaultAzureCredential/KeyVault/stack-adapter token found — confirm auth is resolved via env/stack-adapter, not a literal"`
- [ ] `python -c 'import redis'` (or `redis.asyncio`) · `command -v redis-cli` · `command -v az` (`az redis` extension) → note absent, don't fail
- [ ] a hit-ratio / eviction metric is exported via `observability-gen` (cache health is observable)

## Functional
Warm the cache for a hot key, then mutate the source and confirm the invalidation path serves the FRESH value (not the stale TTL'd one); fire many concurrent misses on one expired key and confirm only a single source load happens (stampede protection holds); finally, take the cache offline and confirm reads still succeed by falling through to the source (fail open) — none of the three should surface a cache error to the caller.
