# Spec — Dashboard UX evolution (in place) — v2 (re-cut)

**Slug:** `dashboard-ux-evolve`
**Status:** v2 — BUILD. Re-cut after red-team `VERDICT: REDESIGN` (code-grounded). The v1
cut re-delivered behavior that already exists; this cut is **NET-NEW only**, split into 2 PRs.
**Created:** 2026-06-28
**Consumes-into:** `/fenrir:plan` → `/fenrir:deliver` → `/fenrir:ship`

## Problem
The dashboard holds *correct* cost/telemetry data but the *access path* to it is slow for
a solo dev: no board search, no way to scope spend to a time window (all-time only), no
at-a-glance "where did the money go." The dark theme is already good → **evolve in place.**

## User & success metric
- **User:** solo dev (repo owner), local, single user.
- **Success metric:** time-to-answer for *"what did I spend this week, and on which US?"*
  drops from "scroll the board / scrape tables" to **one glance + one filter**.

## What already exists — SUBTRACT, do NOT rebuild (red-team, code-verified)
- Kanban per-card USD cost badge — `app.js:717-726`
- Epic + assignee filters — `index.html:196,200`; applied in `visibleStories()` `app.js:615-617`
- Escape-closes-modal — `app.js:796`; focus trap (Tab/Shift+Tab) — `app.js:798-804`
- Kanban column text labels + counts ("In Progress" + badge) — `app.js:124-128, 644-645`
- Readable timestamps in trace + subagent tables (`fmtWhen` ISO→"Jun 27, 21:21") — `app.js:1180, 482`
- Catalog search-box pattern (reusable precedent for the board search) — `index.html:292`
- Whole-board fetch, no pagination (`/api/board` returns full board, `app.py:103-105`) →
  client-side filtering is safe at current solo-scale.

## Scope — NET-NEW cut, split across 2 PRs

### PR1 — frontend-only, low-risk (no backend change)
- **US-1 — Board search box.** Title/id substring search (clone catalog-search at
  `index.html:292`); compose with the existing epic/assignee filters via `visibleStories()`
  (`app.js:615`).
- **US-2 — Top-spenders panel (Overview).** List the 10 costliest US, descending, from
  `/api/board/costs` (`board.py:250`, already client-sortable); row → `openStoryDetail`
  via `board.stories.find(id)`.
- **US-3 — Relative timestamps.** `fmtWhen` → relative ("2h ago") with the absolute time
  on `title` hover; audit + fix any remaining raw-ISO render sites.
- **US-4 — Frontend smoke tests (`qa-tester`).** Playwright: load / search-filters /
  open-modal / Escape — the regression guard the zero-test `app.js` lacks.

### PR2 — backend + frontend, own ADR (bigger blast radius)
- **US-5 — Backend date-window.** Thread `since`/`until` through the event chokepoint
  `_events()` (`app.py:46`), `costs()` + `trace()` (`board.py:250,526`), and the telemetry
  aggregations `summary/by_model/by_skill/by_day/agents/efficiency` (`telemetry.py:138-275`);
  unit tests (`qa-tester`) for 7d/30d/all + boundary.
- **US-6 — Frontend time-range selector** (`7d`/`30d`/`all`) on Overview + Agents +
  Cost-trace, wired to US-5; in-memory module-global range var, reset on reload.

## Acceptance criteria (net-new only)
- **US-1:** typing `auth` filters cards to title/id matches; clearing restores; composes
  with the existing epic + assignee filters.
- **US-2:** Overview shows Top-spenders — 10 costliest US (id + USD, desc); click opens
  that US's detail.
- **US-3:** no raw-ISO timestamp renders anywhere; times show relative text + absolute on hover.
- **US-4:** smoke suite green — app loads, search filters cards, modal opens, Escape closes.
- **US-5:** `costs`/`trace`/telemetry endpoints accept `since`/`until`; aggregations recompute
  on the filtered event set; tests cover the windows + a boundary date.
- **US-6:** selecting `7d` recomputes KPIs + charts + trace to the last 7 days (via US-5);
  `all` restores; the selection persists across Overview↔Agents↔Cost-trace within one load.

## Out of scope
Full rewrite / framework migration; dark-light toggle; real-time WebSocket; CSV export;
audit log; multi-user / durable / committed board state; SSO. **Dropped as redundant:**
status filter (the kanban columns ARE the statuses). **Narrowed:** "across views" = kanban
+ any view that renders through `visibleStories()`. **Deferred to v1.1:** card inline
quick-edit, bulk actions, swimlanes, dedicated cost heatmap (Top-spenders covers the need).

## Chosen stack
FastAPI + vanilla JS SPA + existing dark theme. Routing: visuals via global
**`frontend-design`** skill; wiring + backend params via **`fenrir:coder`**; tests via
**`qa-tester`**. `frontend-gen` skipped (no org-profile `front`; not scaffolding a framework).

## Risks + riskiest assumption (resolved)
- **Resolved:** the v1 "riskiest assumption" (backend already date-filters) is **FALSE** —
  hence US-5 is its own backend PR. Do **PR1 first** to bank value while PR2's ADR is written.
- **Frontend has zero tests** → US-4 (Playwright smoke) is the guard; all `app.js` changes
  are **additive only**, no structural refactor (do not touch drag-drop/modal internals).
- US-5 touches 8 aggregation paths — largest blast radius; isolate in PR2 behind tests.

## Definition of done (per PR)
PR1: US-1..4 criteria pass a manual verify run + smoke suite green; `delivery-gates`
(lint+type+test) green; `/fenrir:ship` PR with this spec + ADR linked, CI green.
PR2: US-5..6 criteria pass; new backend params unit-tested green; own ADR linked.

## Stage ledger (PR1 — feat-40, route=full)
Route numbers: RISK=0, FILES≈6, LOC>80 → full. ADR reused: docs/adr/0007-dashboard-ux-frontend.md.

| Stage | Status | Notes |
|---|---|---|
| plan | done | feat-40; us-104/105/106/107; branch feat/dashboard-ux-frontend |
| architect/ADR | done | 0007 reused (no second ADR) |
| coder us-104 (search) | pending | |
| coder us-105 (top-spenders) | pending | |
| coder us-106 (relative time) | pending | |
| qa us-107 (playwright smoke) | pending | = the `qa` validation stage |
| doc-keeper | pending | CHANGELOG + dashboard README |
| /code-review | pending | |
| reviewer (hygiene) | pending | |
| diff-redteam | pending | |
| delivery-gates | pending | |
| ship | pending | |
