# VERIFY — memory-keeper

Run after `memory-keeper` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] all writes land under the consuming repo's `docs/delivery-memory/` and nothing outside it: `[ -d docs/delivery-memory ] && echo OK || echo MISSING`
- [ ] every `.jsonl` line parses as one JSON object: `while read -r l; do echo "$l" | python3 -c 'import json,sys;json.loads(sys.stdin.read())' || echo BADLINE; done < docs/delivery-memory/gate-exceptions.jsonl`
- [ ] each `gate-exceptions.jsonl` line carries ALL six fixed fields the SessionStart hook depends on — `id`, `rule`, `reason`, `granted_by`, `expires` (`YYYY-MM-DD`), `status` — with no field renamed/dropped: `python3 -c "import json;[print('OK' if {'id','rule','reason','granted_by','expires','status'}<=set(json.loads(l)) else 'MISSING-FIELD') for l in open('docs/delivery-memory/gate-exceptions.jsonl')]"`
- [ ] no waiver was written without a `reason`, a `granted_by` owner, or an `expires` date; `drift-log.jsonl` was appended-only (prior lines unchanged); no secrets/PII/transcripts stored

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v python3` (or `jq`) for the JSONL validation above · `command -v git` (memory is git-tracked) → note absent, don't fail

## Functional
- Re-run `list`: it surfaces exactly the `open` AND non-expired exceptions (expired-but-open flagged "lapsed"), matching what the `session-context` SessionStart hook would inject. After `expire`, the named ids flip to `status: "closed"` with all other fields/line-order preserved.
