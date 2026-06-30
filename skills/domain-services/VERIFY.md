# VERIFY — domain-services

Run after `domain-services` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **`services/` layer** — the use-case file(s) — not the whole repo. A repo-wide search is not falsifiable (an `import fastapi` in `api/` is correct there). Resolve the services file(s) first, then run the co-located checks against them:

```
SVC_FILES=$(find . -path '*/services/*.py' ! -name '__init__.py' ! -path '*/test*' )
echo "${SVC_FILES:-<none — services layer not found, FAIL>}"
```
If `SVC_FILES` is empty, the skill produced no use-case in `services/` → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **no framework objects in the use-case** — the domain stays transport-free: `for f in $SVC_FILES; do grep -nE '\b(fastapi|starlette|flask|django|Request|Response|APIRouter|HTTPException)\b' "$f" && echo "FRAMEWORK-LEAK in $f"; done; [ -z "$(for f in $SVC_FILES; do grep -E '\b(fastapi|starlette|flask|django|Request|Response|APIRouter|HTTPException)\b' "$f"; done)" ] && echo OK || echo FRAMEWORK-IN-SERVICES`
- [ ] **no raw I/O inline** — DB/HTTP/queue access goes through injected ports, not a literal client/session call: `for f in $SVC_FILES; do grep -nE '\b(httpx|requests|aiohttp|urllib)\b|\.(execute|query|cursor)\(|psycopg|sqlalchemy|boto3|azure\.' "$f" && echo "IO-LEAK in $f"; done; [ -z "$(for f in $SVC_FILES; do grep -E '\b(httpx|requests|aiohttp|urllib)\b|\.(execute|query|cursor)\(|psycopg|sqlalchemy|boto3|azure\.' "$f"; done)" ] && echo OK || echo IO-IN-SERVICES`
- [ ] **ports are injected, not instantiated** — collaborators arrive as typed parameters (`Protocol`/ABC) and the use-case is deterministic: `for f in $SVC_FILES; do grep -qE 'Protocol|ABC|abstractmethod|: *[A-Z][A-Za-z]+(Port|Repository|Repo|Client|Gateway|Service)\b' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NO-INJECTED-PORT`
- [ ] **no hidden global / ambient time** — no module-level mutable singleton or wall-clock reach-out (inject a clock instead): `for f in $SVC_FILES; do grep -nE 'datetime\.now\(|datetime\.utcnow\(|time\.time\(|os\.environ|os\.getenv|global ' "$f" && echo "AMBIENT in $f"; done; [ -z "$(for f in $SVC_FILES; do grep -E 'datetime\.now\(|datetime\.utcnow\(|time\.time\(|os\.environ|os\.getenv|global ' "$f"; done)" ] && echo OK || echo AMBIENT-STATE`
- [ ] **explicit domain errors, not raw/HTTP status** — invariants raise typed domain errors, not bare `Exception` or a status code: `for f in $SVC_FILES; do grep -qE 'raise [A-Z][A-Za-z]*Error|raise [A-Z][A-Za-z]*(Exception|Denied|NotFound|Conflict|Invalid)' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NO-DOMAIN-ERROR`
- [ ] **cloud-agnostic** — the layer carries no hard cloud dependency (runs with no `az`/`terraform`/`gh`): `! grep -rEq '\b(az |terraform |subprocess.*\b(az|gh)\b|DefaultAzureCredential)\b' $SVC_FILES && echo OK || echo CLOUD-DEP-IN-SERVICES`

## Informational (does NOT block; note if absent)
- [ ] a port interface lives near its consumers (a `ports.py`/`Protocol` in or beside `services/`) so data-access-coder has a clear contract to implement
- [ ] in/out boundary types are domain/schema types, not ORM models (grep the signatures; note any `models.`/`*ORM` in a service return type)
- [ ] `cd src/<module> && uv run pytest <the service's test>` is present and green (per ADR-0005)

## Functional
Instantiate a use-case with **fake ports only** (in-memory stubs satisfying each `Protocol`) — no DB, no network — and assert: the happy path returns the expected domain result; each business invariant that should fail raises its specific domain error; and the same inputs + injected ports always produce the same output (determinism). The whole exercise must run with no infrastructure and no cloud CLI on PATH.
