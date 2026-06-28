---
description: Plan-first — the FIRST step of any feature. Decompose the work into Epic → Feature → atomic User Stories on the dashboard board (reusing existing items, never an umbrella US), then create the feat/<feature> branch. Writes the plan only; NO code. /fenrir:deliver then builds the US one at a time with per-US cost tracking. Fuzzy idea? run /fenrir:challenge-me first to scope it.
---

# /fenrir:plan

Development starts on the **board**, not in the editor. This command turns a piece of work into a
proper agile breakdown — one business **Feature**, its **atomic User Stories** (one thing each) —
*before* a line of code, so the work is planned and trackable from the start. One Feature = one
branch = one PR.

## When to use
- Starting a new feature / change with a reasonably clear intent.
- A fuzzy idea? → run `/fenrir:challenge-me` first to scope it, then plan.
- `/fenrir:deliver` and `/fenrir:challenge-me` call this automatically when no plan exists (see their preconditions).

## What it produces
- A business **Feature** on the board under the right **Epic** (reuse an existing Epic/Feature when the work fits; create only if needed).
- Its **atomic US** — each solves exactly ONE thing, with one clear acceptance criterion. Multi-step work → Tasks under a US, not more US.
- A `feat/<feature-slug>` branch.
- **No code.** Planning only.

## Steps
1. **Read the board first.** `cd dashboard && python -m backend.cli list`. Reuse an existing Epic/Feature if the work belongs there; never duplicate.
2. **Decompose** (delegate to the `delivery-tracker` agent, which owns this): work → ONE Feature (a capability a stakeholder would name) → atomic US. Apply the doctrine — no per-session/umbrella US; if a US would do more than one thing or carry an outsized share of its epic, split it. Give each US `--as-a/--i-want/--so-that` + one `--ac`.
3. **Check granularity.** `python -m backend.cli audit` — fix any US it flags as an umbrella (decompose it). Atomic-but-expensive US are fine (they show under `expensive_us`).
4. **Commit the planned US to `todo`.** `cli story add` defaults to `backlog` (= a maybe-someday idea); the work you just planned is committed, so move each planned US to **todo**: `python -m backend.cli move --kind story --id <us> --status todo`. Leave only genuine later-ideas in backlog.
5. **Branch.** `git checkout -b feat/<feature-slug>` — one Feature, one branch, one PR.
6. **Print the plan** — the Feature id + its US ids in build order — and STOP. No code at this stage.

## Then
- `/fenrir:deliver` builds the US **one at a time**: `python3 scripts/track_session.py set-us --id <us>` before each, so its real cost lands on that US (Epic = Σ Features = Σ US).
- The PR for this branch delivers the Feature's US; reference them in the PR body so the `delivery-trace` check passes.

## Refuses / degrades
- No `dashboard/` companion app → say board tracking is unavailable here; still create the branch and drop the breakdown into `docs/specs/<feature>.md` so the plan exists somewhere.
- Asked to write code → decline; that is `/fenrir:deliver`. This command plans only.
