# VERIFY — report

Run after `report` has produced a session digest. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the report has all five sections in order — Changed, Decisions, Tests, Cost, Board: `for s in Changed Decisions Tests Cost Board; do grep -qi "$s" report-output.md || echo "MISSING $s"; done; echo OK`
- [ ] cost is REAL, sourced from dashboard telemetry/trace and not fabricated, with USD labeled DERIVED: `( cd dashboard && python -m backend.cli trace >/dev/null 2>&1 ) && echo OK || echo "MISSING (cost must degrade to 'unavailable')"`
- [ ] it degrades honestly: when `dashboard/` is absent the Cost section says "unavailable" rather than inventing numbers — `[ -d dashboard ] && echo "dashboard present: cost expected" || grep -qi "cost.*unavailable" report-output.md && echo OK || echo MISSING`
- [ ] board moves are tagged as INFERRED from session actions, not a recorded timeline (the board store keeps only current status): `grep -qi "infer" report-output.md && echo OK || echo MISSING`
- [ ] it is session-scoped and explicitly distinct from `/fenrir:status` (repo gate state) and `us-cost-tracking` (per-US cost) — both named as the owning siblings
- [ ] read-only: the run wrote nothing to gate-exceptions / branch-protection / the board governance state (no mutation)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v git` · `command -v python` · the companion app: `( cd dashboard && python -m backend.cli list >/dev/null 2>&1 ) && echo dashboard-ok || echo "dashboard absent — git-only mode"` → note absent, don't fail
- [ ] cost is understood as a derived ESTIMATE (price book in `dashboard/backend/pricing.py`), not billed dollars

## Functional
- In a session that changed files, ran tests, and touched the board, run the skill: the report's Changed/Decisions/Tests reflect the real git + transcript record, the Cost figure matches `python -m backend.cli trace` (and `/api/trace`) for the session with USD labeled DERIVED, and the Board section lists the items touched flagged as inferred. Then run it with `dashboard/` unreachable and confirm it degrades to git-only with an explicit "cost unavailable" note instead of fabricating numbers.
