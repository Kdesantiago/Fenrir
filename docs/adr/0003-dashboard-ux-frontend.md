# 0003 — Dashboard UX PR1: additive frontend + isolated Playwright harness

- Status: Accepted
- Date: 2026-06-28
- Deciders: architect agent
- Profile: framework=fastapi; front=vanilla JS SPA (spec §"Chosen stack", line 71). NOTE: `templates/org-profile.yaml:9` declares `front: streamlit`, but that file is the consumer template default — Fenrir's OWN dashboard ships a hand-written vanilla-JS SPA (`dashboard/frontend/app.js`, `index.html`). No org-profile governs this repo's dashboard; spec is authoritative.

## Context
PR1 of `dashboard-ux-evolve` (spec: `docs/specs/dashboard-ux-evolve.md`). NET-NEW frontend only: US-1 board search, US-2 Top-spenders panel, US-3 relative timestamps, US-4 Playwright smoke.
Forces:
- `dashboard/frontend/app.js` ~1382L, **zero tests**. Drag-drop/modal/render internals are untested → any structural change risks silent regression.
- Repo is Python-pure. CI gate `ci.yml:106-122` runs a `dashboard` job (`working-directory: dashboard`, `uv run pytest`) — ruff+mypy+pytest only, **no Node step**. Local gate `.pre-commit-config.yaml` is Python/secret/format only. Adding JS tooling must not perturb either.
- Existing filter chain `visibleStories()` (`app.js:614-619`) already composes epic+assignee. Catalog search input precedent exists (`index.html:292`).
- Cost rollup endpoint `GET /api/board/costs` exists (`board.py:250`) returning per-US cost, client-sortable.

## Decision
1. **Additive-only `app.js`.** New UX is ADDED alongside existing code. **Binding constraint:** do NOT refactor drag-drop, modal/focus-trap (`app.js:796-804`), or render internals in PR1. New functions + new DOM hooks only; touch existing functions only to ADD a filter predicate or call site.
2. **Playwright as an ISOLATED Node dev-dependency under `dashboard/`.** Own `dashboard/package.json` + `playwright.config.*` + `dashboard/tests/e2e/`. **NOT wired into** the Python pytest path, `ci.yml`, or `.pre-commit-config.yaml`. v1 = **local-only** regression guard (run by hand / qa-tester). No Node CI job added in PR1; a `playwright` CI step is **deferred** until a Node runner is explicitly justified. Isolation keeps the existing `dashboard` Python gate green and unchanged.
3. **Top-spenders reuses `GET /api/board/costs`** (`board.py:250`), sorted **client-side desc**, sliced top 10. **NO new endpoint, NO backend slice in PR1.** Row click → `openStoryDetail` via `board.stories.find(id)`.
4. **Search extends `visibleStories()`** (`app.js:614`): add one title/id substring predicate to the existing chain; clone the `index.html:292` search-input pattern for the board toolbar. **No parallel filtering path.**

## Alternatives considered
- **Refactor app.js while adding UX** — rejected: zero tests + 1382L = high silent-regression risk; PR1's value is additive and must not destabilize drag-drop/modal.
- **No JS tests, manual verify only (option b)** — rejected: leaves the SPA permanently unguarded; US-4 explicitly wants the regression guard the file lacks. Cost of an isolated harness is low and self-contained.
- **Playwright wired into pytest / root pre-commit / ci.yml now** — rejected for PR1: forces a Node toolchain onto the Python required check, slows the gate, and risks flaky-e2e blocking merges before the suite is proven. Promote to CI later as a separate decision.
- **New `/api/board/top-spenders` endpoint** — rejected: `costs()` already returns sortable per-US data; a new endpoint grows backend blast radius the spec scopes to PR2.

## Consequences
- (+) Existing Python CI/pre-commit gates untouched; merge stays green without a Node runner.
- (+) SPA gains a real (if local) regression guard; backend unchanged.
- (-) Smoke suite is **not enforced in CI** for v1 — green-ness depends on dev/qa discipline. Tracked as deferred follow-up: add a Node CI job.
- (-) Top-spenders correctness is bounded by `costs()` output shape; if that contract changes, US-2 silently breaks (no backend test added here).
- Commits the team to: never refactor app.js internals under this feature; new Node toolchain lives ONLY under `dashboard/` and out of the Python path.

## Implementation notes for downstream
- **coder:** US-1 add substring predicate inside `visibleStories()` (`app.js:614`) + clone `index.html:292` input into the board toolbar, wire to existing `filters` + re-render. US-2 new Overview panel: fetch `/api/board/costs`, sort desc client-side, top 10, row→`openStoryDetail`. US-3 convert `fmtWhen` (`app.js:1180,482`) to relative text with absolute ISO on `title`; audit all render sites for raw ISO. **Do not modify drag-drop/modal/focus-trap internals.**
- **qa-tester:** US-4 Playwright suite under `dashboard/tests/e2e/` with own `dashboard/package.json`+config; cover load / search-filters-cards / open-modal / Escape-closes. Keep `package.json` deps + `node_modules` out of the Python build; do NOT add it to `ci.yml` or `.pre-commit-config.yaml`.
- **reviewer:** verify (a) zero diff to drag-drop/modal/render internals; (b) no new backend endpoint; (c) search goes through `visibleStories()`, not a parallel path; (d) Node tooling is confined to `dashboard/` and absent from `ci.yml:106-122` + `.pre-commit-config.yaml` (Python `dashboard` gate must be byte-unaffected); (e) no raw-ISO timestamps remain.
