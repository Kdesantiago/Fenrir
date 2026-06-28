# Spec — Package quality hardening

**Slug:** `package-quality-hardening`
**Status:** DEFERRED — second feature, build AFTER `dashboard-ux-evolve` PR merges.
**Created:** 2026-06-28

## Why deferred
Sequenced second per the challenge-me decision (dashboard UX first = most visible value;
quality core second = protects the cost-truth foundation). Specced now so the cut is
remembered and not silently re-expanded. **Do not build in the dashboard-UX PR.**

## Problem
Fenrir's value prop is *trustworthy gated delivery with per-US cost truth*. Two things
undercut it: (1) the cost-attribution core (`scripts/track_session.py`, 555L + the
tracking hooks) is a single point of failure that is **undertested and swallows errors
silently** — the numbers the dashboard shows could be quietly wrong; (2) core modules
have grown monolithic, raising change-risk.

## Scope (two tracks, both confirmed in scope for this feature)

### Track 1 — Correctness / reliability (do first within this feature)
- Integration test for the full hook pipeline: `tracking-open` → work → git commit →
  `tracking-attribute` → `tracking-collect` → `tracking-finalize`, asserting cost lands
  on the right US with no double-count.
- Unit tests for the 3 undertested hooks: `tracking-open.py`, `tracking-collect.py`,
  `tracking-guard.py` (185L, strict-mode gate — needs isolated coverage).
- Replace blanket `except Exception:` in tracking hooks with specific exceptions
  (`json.JSONDecodeError`, `subprocess.CalledProcessError`, `OSError`) and **log to
  stderr** before failing open (keep fail-open behavior; kill the silence).
- De-SPOF `track_session.py`: extract the cost/attribution logic into importable pure
  functions so it is unit-testable without subprocess round-trips.

### Track 2 — Maintainability / docs
- Split `dashboard/backend/board.py` (678L) and `telemetry.py` (396L) into cohesive
  modules (CRUD / cost-rollup / reassignment; parse / aggregate / price) — behavior-
  preserving, tests stay green.
- Add a README index to `skills/`, `agents/`, `hooks/`, `commands/` (one-line summary
  table per dir; the catalog data exists in `dashboard/backend/catalog.py` — reuse it).
- Tighten type hints in the dashboard data layer (replace broad `dict[str, Any]`).

## Out of scope
Behavior changes to the cost model; dashboard UX (that's the other feature); anything
touching the solo-vs-team durability question (user is solo → board-durability gap is
explicitly NOT a quality target here).

## Acceptance criteria
- New integration + unit tests added and green; coverage on `track_session.py` and the
  3 hooks demonstrably present.
- No blanket `except Exception:` remains in the tracking hooks without a logged reason.
- `board.py` / `telemetry.py` split with the existing 146 backend tests still green.
- README index present in the four dirs; no stale entries (every listed item exists).

## Riskiest assumption
That `board.py`/`telemetry.py` can be split **behavior-preserving** under the existing
test suite. If coverage has blind spots, the split could pass tests but change behavior —
add characterization tests before splitting.
