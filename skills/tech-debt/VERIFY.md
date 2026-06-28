# VERIFY — tech-debt

Run after `tech-debt` has cataloged debt + drift and filed items onto the board. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the inventory carries a `debt` dimension: at least one `debt` item (marker / skipped-test / stale-dep / complexity / missing-test). For drift: IF `docs/dat/` OR `docs/adr/` exists (`ls "$CLAUDE_PROJECT_DIR"/docs/dat/*.md "$CLAUDE_PROJECT_DIR"/docs/adr/*.md 2>/dev/null`), drift was checked and every `drift` item names the violated doc + section AND the `file:line` that contradicts it; if BOTH are absent the report says "no recorded design" and skips drift (a greenfield repo still passes)
- [ ] every item has a `file:line` location and an impact×effort rating; the list is ordered by rank (not an unranked dump)
- [ ] items were filed onto the board, not just listed: EXACTLY ONE "Tech debt" epic exists (idempotent — no duplicate per sweep): `cd "$CLAUDE_PROJECT_DIR"/dashboard && python -m backend.cli list | grep -c '^.*Tech debt'` equals 1; and the count of filed stories carrying a `file:line` token is at least the inventory row count: `python -m backend.cli list | grep -c ':[0-9]'` ≥ rows — OR, if `dashboard/` is absent, the report says items could NOT be filed and emits the full inventory (the tracking step was not silently dropped)
- [ ] the skill changed ONLY board data — no source/DAT/ADR edits: `cd "$CLAUDE_PROJECT_DIR" && git diff --name-only | grep -v '^dashboard/data/boards/'` is EMPTY
- [ ] if `org-profile.yaml` `framework` is unset OR `none`, the skill refused (no app-code idioms to scan)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `docs/dat/` exists (`ls "$CLAUDE_PROJECT_DIR"/docs/dat 2>/dev/null` — drift scored against DATs + ADRs); if absent, note drift was scored against `docs/adr/` only
- [ ] the companion `dashboard/` app is runnable for filing → note absent and emit inventory-only

## Functional
- Each filed story is traceable back to one inventory row (title carries `file:line` + the "resolved" AC); a planner can pick the top-ranked item and act on it without re-deriving anything.
- An accepted won't-fix-now deviation appears as a `memory-keeper` waiver (owner + expiry), not as an open story.
