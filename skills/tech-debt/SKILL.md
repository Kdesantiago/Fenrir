---
name: tech-debt
description: Use when you want to CATALOG tech-debt and DETECT architecture drift, then file the items onto the board so debt is tracked not lost — find markers (TODO/FIXME/HACK), skipped tests, deprecated deps, complexity hotspots, missing tests on risk paths, AND code that contradicts the recorded design (docs/dat DATs + docs/adr ADRs). Prioritize by impact×effort, create board items via the dashboard CLI under a "Tech debt" epic/feature. Triggers — "catalog the tech debt", "what's drifted from our design", "find the debt and put it on the board". NOT refactor/simplify (those FIX code), NOT dat-architect (writes the DAT — this detects drift FROM it). Reads org-profile.yaml `framework`.
---

# Tech Debt — catalog + drift detection

Surface the debt the codebase is carrying and the places it has drifted from its own recorded
design, then **file each item onto the board** so it is tracked work, not a lost note. This skill
CATALOGS and PRIORITIZES — it does NOT fix code and does NOT write the design doc. The deliverable
is a prioritized inventory plus board items created via the dashboard CLI.

## When to use
- "catalog / inventory the tech debt", "where are we cutting corners", "find the FIXMEs and track them"
- "what has drifted from our DAT/ADRs", "does the code still match the recorded design"
- Periodic debt sweep before planning, or after a fast-moving feature spree

## When NOT to use
- FIXING the debt — restructure without behavior change → `refactor`; in-place reduction/KISS → `simplify`; behavior change/feature → `/fenrir:deliver`
- WRITING or auditing the architecture doc itself → `dat-architect` (this skill detects drift FROM the DAT; it does not author it)
- Recording a deliberate, accepted deviation as a waiver with an owner+expiry → `memory-keeper` (`waive`)
- Per-US token/cost tracking → `us-cost-tracking`; running lint/type/test gates → `delivery-gates`

## Inputs
- `org-profile.yaml` → `framework` (selects test-skip + dep-manifest idioms: `fastapi`/`streamlit` → pytest `@pytest.mark.skip`, `requirements.txt`/`pyproject.toml`; `express` → jest `.skip`, `package.json`; `spring` → JUnit `@Disabled`, `pom.xml`)
- The repo source tree (for markers, skipped tests, complexity, dep manifests)
- The recorded design: `docs/dat/*.md` (DATs) + `docs/adr/*.md` (ADRs) — the source of truth drift is measured against
- The companion `dashboard/` app (its `backend.cli` + board) — where items are filed

## Steps
1. Read `org-profile.yaml`; resolve `framework` (drives the skip-marker + dep-manifest patterns to scan).
2. **Catalog debt** (cite `file:line` for each):
   - **Markers** — `TODO` / `FIXME` / `HACK` / `XXX` across source.
   - **Skipped / disabled tests** — `@pytest.mark.skip`, `it.skip`/`xit`, `@Disabled`, commented-out test bodies.
   - **Deprecated / stale deps** — pinned-old or deprecated packages in the manifest/lockfile.
   - **Complexity hotspots** — oversized functions/files, deep nesting, god-objects.
   - **Missing tests on risk paths** — auth, money, deletion, external I/O with no covering test.
3. **Detect drift vs the recorded design** — read `docs/dat/*.md` + `docs/adr/*.md`; flag code that CONTRADICTS a recorded decision (e.g. an ADR picks Postgres but code talks to Dynamo; the DAT says all writes go through a service but a module writes direct). Each drift item names the document + section it violates and the `file:line` that contradicts it. If `docs/dat/` is absent, score drift against ADRs only (note the gap); if BOTH `docs/dat/` and `docs/adr/` are absent, report "no recorded design to measure drift against" and emit a debt-only inventory — do not invent a baseline or hard-require drift.
4. **Prioritize** every item by **impact × effort** (low/med/high each) → a simple rank; surface the high-impact/low-effort items first. `--points` is a single integer, so map effort to points — **low=1, med=3, high=8** — pass that int and keep the impact dimension in the title/AC ("low/med/high" passed to `--points` fails the int parse).
5. **File onto the board** so nothing is lost. **Get-or-create the home — never blind-add:** `epic add` always mints a NEW id, so a blind `epic add "Tech debt"` duplicates the epic on every sweep. Run from `dashboard/`:
   - Epic (get-or-create): run `python -m backend.cli list` FIRST; if a "Tech debt" epic already exists, REUSE its id; only run `python -m backend.cli epic add --title "Tech debt"` when none exists.
   - Feature: `python -m backend.cli feature add --epic <epic-id> --title "Debt — <area>"`.
   - Item: `python -m backend.cli story add --feature <feat-id> --title "<debt|drift>: <what> (<file:line>)" --points <1|3|8> --ac "<the fix / what 'resolved' means>"`.
   - For a deliberate, accepted deviation (won't-fix-now with a reason), record a waiver via `memory-keeper` instead of a story.
6. Report the inventory + the created board item ids; do not fix anything (route fixes to `refactor`/`simplify`/`deliver`).

## Output
- A prioritized debt + drift inventory — `item | kind (debt|drift) | location (file:line) | violates (doc§ for drift) | impact×effort | board id` — top items first.
- The board items actually created (their ids), under a "Tech debt" epic/feature, so the debt is tracked.
- A one-line carve reminder: this CATALOGS + files; it does not FIX (that is refactor/simplify/deliver) and does not WRITE the DAT (that is dat-architect).

## Refuses when
- `framework` is unset OR `none` in `org-profile.yaml` (no app-code idioms to scan — the skip-marker / dep-manifest patterns are undefined) — report which and stop.
- Asked to FIX the debt or to WRITE/edit the DAT/ADR — out of lane; route to refactor/simplify/deliver or dat-architect.
- Asked to flag drift without reading `docs/dat/`+`docs/adr/` — drift is measured against the recorded design, not asserted from opinion.
- The `dashboard/` app is absent — say items cannot be filed and emit the inventory only (do not silently drop the tracking step).
