# Spec v2 — Cost fidelity, per-run attribution, clear kanban cost

- Status: Accepted (v2 — redesigned after red-team VERDICT: REDESIGN)
- Date: 2026-06-27
- Slug: cost-fidelity

## What v1 got killed for → v2 fixes
- **link + per-run attribute double-count** (runs ⊂ a session's subagent events) → v2: one
  attribution mechanism per session. `attribute` records the run's `session_id`; `link`
  refuses a session that already has per-run attributions, and `attribute` refuses a run
  whose session is already whole-session `link`ed. Board cost = work_log only (telemetry
  reconciliation untouched).
- **`toolUseId` absent on 67/72 runs** → v2: attribute by a stable synthetic `run_id`
  (the `agent-<id>` meta stem), which `subagent_runs` now exposes; idempotency key `(run_id, US)`.
- **Wrong root-cause of the "$450 on us-13 & us-15"** → re-diagnosed: us-13 is a manual
  whole-repo entry (`session_id=""`, note "all Fenrir telemetry"), us-15 is one session; they
  coincide because that session ≈ all telemetry. Fix = **clean the dogfood data** (separate
  commit), not a same-session guard. Don't delete blindly: us-13's whole-repo lump is removed
  with rationale; real per-run attributions replace the fakes so US show DISTINCT real costs.
- **PRICES arity breaks pinned tests** → v2 lists the exact test edits; rates are DERIVED.
- **Cache-rate drift** → store base `(input, output)` + a shared `CACHE` multiplier map;
  derive 5m/1h/read so a contract change is one number.
- **Modal doesn't show epic/feature rollup today** → adding it is explicit scope here.
- **`has_session_for` single-item / blind to `session_id==""`** → add board-wide
  `stories_for_session()`; documented that session-less manual entries are invisible to it.

## Design

### C. Pricing fidelity
- `PRICES[family] = (input, output)` USD/1M; shared `CACHE = {"w5m":1.25, "w1h":2.0, "read":0.1}`.
  `rates_for(model)` returns `{input, output, w5m, w1h, read}` deriving cache from input
  (strip `[..]` tier suffix first). Families: opus (15,75), sonnet (3,15), haiku (1,5),
  fable=opus, default=sonnet.
- `cost_of(usage, model)` = input×in + output×out **(output already includes extended-thinking
  tokens — verified: no separate field, 211 thinking blocks billed as output)** + cache_read×read
  + cache write split from `usage.cache_creation`: `ephemeral_5m`×w5m + `ephemeral_1h`×w1h;
  if the sub-dict is absent, fall back to `cache_creation_input_tokens`×w5m (flagged, synthetic-only).
- Document the model + named gaps (web-search `server_tool_use`, batch/priority `service_tier`,
  `[1m]` long-context premium) in pricing.py + dashboard README.
- **Test edits (required):** update `test_pricing.py` opus tuple assertion + `cost_of` block to
  the derived rates; add a test that a 1h-cache-heavy block costs > the same tokens as 5m.

### A. Per-run attribution (distinct, real, no double-count)
- `telemetry.subagent_runs` exposes a stable `run_id` (the `agent-<id>` stem) + existing
  `session_id` per run.
- `cli attribute --us <id> --run <run_id>`: write a WorkLogEntry from that run's REAL
  tokens/cost (`source=telemetry-run`, `subagent_type=<type>`, `session_id=<run session>`),
  idempotent per `(run_id, US)`. Distinct runs → distinct US costs.
- **Exclusivity guard:** `board.stories_for_session(sid)` (scans all stories+tasks). `attribute`
  refuses if the run's session is already whole-session `link`ed to a US; `link` refuses/warns
  if the session already has `telemetry-run` attributions. (Both blind to `session_id==""`
  manual entries — documented.)
- **Clean the dogfood (separate data commit):** remove the bogus identical `$450` lumps on
  us-13 (whole-repo) and us-15 (whole-session); re-attribute a few DISTINCT real subagent runs
  to their stories so the board shows honest, varied per-US costs.

### B. Kanban cost clarity
- Card shows ONE labeled US-own cost line (e.g. `US cost · $X · N tok`), only when work_log
  exists. **Remove the unlabeled epic/feature `$900.06` rollup chips from cards.**
- **Add an epic/feature rollup line to the story modal** (the rollup the badges used to hint),
  labeled, from `/api/board/costs`.

## Acceptance criteria
- `rates_for` returns derived 5m/1h/read; `cost_of` prices 1h > 5m for equal tokens; thinking
  (as output) covered; fallback path tested (synthetic). Pinned pricing tests updated → green.
- `subagent_runs` records `run_id`; `cli attribute --run` attaches a single run's real cost
  (idempotent per run_id+US); two US attributed to two different runs show DIFFERENT costs.
- `attribute`↔`link` exclusivity enforced via `stories_for_session`; a test proves no
  double-count path (link a session, then attribute one of its runs to another US → refused).
- Kanban card: one labeled US-own cost line, no rollup chips; modal shows per-agent + an
  epic/feature rollup. Verified against the running app.
- Dogfood board no longer shows identical lumps; ruff+mypy clean; tests green; README+CHANGELOG.

## Out of scope (named)
- Auto-splitting a session's main-thread spend across US (no per-US signal in one session).
- Reconciling against `session_id==""` manual entries in the exclusivity guard.
- Web-search request cost, batch/priority tiers, `[1m]` long-context premium (documented gaps).
