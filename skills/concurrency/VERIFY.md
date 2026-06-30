# VERIFY — concurrency

Run after `concurrency` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **touched concurrent module(s)** — the file(s) running async/threaded work or guarding shared state — not the whole repo. A repo-wide search is not falsifiable (a stray `async def`, a lone `Lock`, or a `gather` would pass with zero correctness work). Resolve the concurrent file(s) first, then run the co-located checks against them:

```
CC_FILES=$(grep -rlE 'asyncio|async def|await |threading\.|Thread\(|Lock\(|Semaphore|gather\(|TaskGroup|run_in_executor|to_thread' --include='*.py' . )
echo "${CC_FILES:-<none — no concurrent module found, FAIL>}"
```
If `CC_FILES` is empty, the skill produced no wired concurrent code → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **no blocking call on the loop** — no sync sleep / sync I/O inline in async code: `for f in $CC_FILES; do grep -nqE '^\s*time\.sleep\(|requests\.(get|post)|\.read\(\)\s*$' "$f" && echo "BLOCK in $f"; done; [ -z "$(for f in $CC_FILES; do grep -E '^\s*time\.sleep\(|requests\.(get|post)' "$f"; done)" ] && echo OK || echo LOOP-BLOCKING-CALL`
- [ ] **bounded waits** — awaits/lock acquires carry a timeout, not an unbounded hang: `for f in $CC_FILES; do grep -qE 'asyncio\.timeout|wait_for|\.acquire\(.*timeout|timeout=' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-TIMEOUT`
- [ ] **shared state guarded** — a lock/semaphore (or message-passing) protects mutated shared state: `for f in $CC_FILES; do grep -qE 'Lock\(|RLock\(|Semaphore\(|async with .*lock|with .*lock|Queue\(' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-GUARD`
- [ ] **bounded parallelism** — fan-out is capped (semaphore / bounded pool), not an unbounded gather: `for f in $CC_FILES; do grep -qE 'gather\(|as_completed' "$f" && ! grep -qE 'Semaphore|max_workers|bounded|limit|chunk' "$f" && echo "UNBOUNDED in $f"; done; [ -z "$(for f in $CC_FILES; do grep -E 'gather\(' "$f" | grep -qvE 'Semaphore' && grep -LE 'Semaphore|max_workers|limit|chunk' "$f"; done)" ] && echo OK || echo UNBOUNDED-FANOUT`
- [ ] **cancellation-safe** — `CancelledError` is not swallowed and cleanup runs in `finally` (skip-OK only if the file spawns no task): `for f in $CC_FILES; do grep -qE 'except\s+asyncio\.CancelledError\s*:\s*(pass|\.\.\.)\s*$' "$f" && echo "SWALLOW in $f"; done; [ -z "$(for f in $CC_FILES; do grep -E 'except\s+asyncio\.CancelledError\s*:\s*(pass|\.\.\.)\s*$' "$f"; done)" ] && echo OK || echo SWALLOWED-CANCEL`
- [ ] **tasks tracked, not fire-and-forget** — spawned tasks are referenced/awaited (`TaskGroup` or a held reference), not orphaned: `for f in $CC_FILES; do grep -qE 'TaskGroup|create_task' "$f" && grep -qE 'async with .*TaskGroup|=\s*.*create_task|await ' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NOTE-confirm-no-orphan-task`
- [ ] (profile-driven) `framework` in `org-profile.yaml` is the supported (Python FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] **structured-concurrency primitive present** — advisory, NOT a gate (`TaskGroup`/`anyio` preferred over bare `create_task`+`gather`): `for f in $CC_FILES; do grep -qE 'TaskGroup|anyio|trio' "$f" && echo "structured concurrency in $f"; done | grep -q . && echo OK || echo "NOTE: bare create_task/gather — confirm tasks are tracked + cancellable"`
- [ ] contention/queue-depth/cancellation signals are emitted via `observability-gen` (concurrency behavior is observable)
- [ ] core is **ZERO cloud** — no `az`/`terraform`/`kubectl`/`gh` in the touched module; a distributed-lock (blob-lease/Redis) note appears ONLY when `org-profile.yaml` `cloud_layer` opts in — never a hard dependency

## Functional
Exercise the concurrent code under interleaving against the touched module: (1) run the hot path under concurrent load → shared state stays consistent (no lost update / corrupted aggregate — race-free); (2) stub a slow dependency → the bounded await TIMES OUT within its bound, it does not hang the loop; (3) cancel a task mid-flight → `finally` cleanup runs, `CancelledError` propagates, and no task leaks; (4) fan out over a large input → the semaphore/bounded pool caps in-flight work, it does not exhaust connections/memory; the loop never blocks on a sync call throughout.
