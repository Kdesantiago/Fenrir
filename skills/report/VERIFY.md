# VERIFY — report

Run after `report` has produced a session digest. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the report has all five sections in order — Changed, Decisions, Tests, Cost, Board: `for s in Changed Decisions Tests Cost Board; do grep -qi "$s" report-output.md || echo "MISSING $s"; done; echo OK`
- [ ] cost is either REAL (reconciled against a linked US, not just "trace ran") or honestly "unavailable" — never fabricated. If the Cost section quotes a USD figure, it must equal the linked story's real `trace --us` total: `usd=$(grep -oiE '\$[0-9]+\.[0-9]+' report-output.md | head -1 | tr -d '$'); if [ -z "$usd" ]; then grep -qi "cost.*unavailable" report-output.md && echo "OK (unavailable)" || echo "MISSING (no figure and no unavailable note)"; else us=$(grep -oiE 'US-[0-9]+|US[0-9]+' report-output.md | head -1); t=$(cd dashboard && python -m backend.cli trace --us "$us" 2>/dev/null | grep -oiE 'total \$[0-9]+\.[0-9]+' | grep -oiE '[0-9]+\.[0-9]+'); [ "$usd" = "$t" ] && echo OK || echo "MISMATCH report=$usd trace=$t"; fi`
- [ ] it degrades honestly: when `dashboard/` is absent the Cost section says "unavailable" rather than inventing numbers — `if [ -d dashboard ]; then echo "dashboard present: cost expected"; else grep -qi "cost.*unavailable" report-output.md && echo OK || echo MISSING; fi`
- [ ] board moves are read from each item's real `transitions[]` timeline (from_status → to_status + `at`), not invented or hand-waved as "inferred": the Board section reflects actual status changes recorded by `set_status` — `grep -qiE 'backlog|todo|in[_ -]?progress|review|done|→|->' report-output.md && echo OK || echo "MISSING transition detail"`
- [ ] it is session-scoped and explicitly distinct from `/fenrir:status` (repo gate state) and `us-cost-tracking` (per-US cost) — both named as the owning siblings
- [ ] read-only: the run wrote nothing to gate-exceptions / branch-protection / the board governance state (no mutation)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v git` · `command -v python` · the companion app: `( cd dashboard && python -m backend.cli list >/dev/null 2>&1 ) && echo dashboard-ok || echo "dashboard absent — git-only mode"` → note absent, don't fail
- [ ] cost is understood as a derived ESTIMATE (price book in `dashboard/backend/pricing.py`), not billed dollars

## Functional
- In a session that changed files, ran tests, and touched the board, run the skill: the report's Changed/Decisions/Tests reflect the real git + transcript record, and the Board section lists the items touched using each item's real `transitions[]` timeline (actual status changes, not an inference). For Cost: if this session's work was linked to a story via `us-cost-tracking`, the figure equals `python -m backend.cli trace --us <id>` (and `/api/trace`) for that US with USD labeled DERIVED and presented as the US's cost (not a session figure); if NO US was linked, confirm Cost reads "unavailable (no per-session cost surface)" rather than relabeling board-wide/per-project telemetry as "this session". Then run it with `dashboard/` unreachable and confirm it degrades to git-only with an explicit "cost unavailable" note instead of fabricating numbers.
