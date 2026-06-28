# Decision — Dashboard UX + package-quality scoping (challenge-me session)

**Date:** 2026-06-28
**Context:** `/fenrir:challenge-me` on the raw idea "improve the package + redesign the
dashboard UI/UX." Two scouts mapped the package and the dashboard before scoping.

## Decisions
1. **Two separate features, sequenced** — *dashboard UX first*, *package-quality second*.
   Not bundled (a single PR touching both = unreviewable).
2. **Dashboard: evolve in place, do NOT rewrite.** Keep FastAPI + vanilla JS + the
   existing dark theme. Add usability (search/filter, time-range, cost surfacing, a11y
   polish). Rationale: theme already ~8/10; backend has 146 passing tests; a framework
   rewrite throws away 1382L working JS to re-earn existing quality.
3. **User is solo + local.** This drops, from scope entirely: multi-user, durable/
   committed/shared board state, SSO, real-time WebSocket, CSV export, audit log. Big cut.
4. **Quality feature = correctness + maintainability**, but **DEFERRED** to the second
   PR (built only after the dashboard-UX PR merges).

## Deferred scope (remembered so it is not silently re-expanded)
- **Deferred to feature #2** (`docs/specs/package-quality-hardening.md`): hook-pipeline
  integration test; unit tests for `tracking-open/collect/guard`; replace silent
  `except Exception` with logged failures; de-SPOF `track_session.py`; split
  `board.py`/`telemetry.py`; README indexes; type-hint tightening.
- **Deferred to dashboard v1.1** (NOT in the UX v1 PR): card inline quick-edit, bulk
  actions, swimlanes, dedicated cost heatmap.

## Alternatives rejected
- Full frontend rewrite to React/Vue via `frontend-gen` — rejected (cost > value; throws
  away tested working code; no org-profile `front` declared).
- Bundling both streams into one feature — rejected (violates smallest-slice; slow review).
- Fixing all ~11 scout-found gaps at once — rejected (roadmap, not a v1).

## Artifacts
- Specs: `docs/specs/dashboard-ux-evolve.md` (BUILD), `docs/specs/package-quality-hardening.md` (DEFERRED).
- ADR: to be written by the architect during `/fenrir:plan` for the dashboard UX feature.
