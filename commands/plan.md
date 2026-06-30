---
description: Plan-first — the FIRST step of any feature. Decompose the work into Epic → Feature → atomic User Stories on the dashboard board (reusing existing items, never an umbrella US), have the architect frame the load-bearing design + ADR, then create the feat/<feature> branch. Writes the plan + ADR only; NO code. /fenrir:deliver then builds the US one at a time with per-US cost tracking. Fuzzy idea? run /fenrir:challenge-me first to scope it.
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

> **A Feature normally groups SEVERAL atomic US** — it's a business *capability*, not a single task. Do **not** fragment one piece of work into many one-US features (that's harder to follow): bundle the related atomic US under one Feature. A 1-US feature is acceptable only when the US is genuinely a standalone capability; if an epic ends up with several open single-US features, group them. `cli audit` flags this as a `thin_features` smell (open features only — merged history isn't nagged). **Still one Feature = one branch = one PR = one patch:** a multi-US Feature is delivered on a single branch with its US built/committed incrementally (`set-us` before each), shipped as one PR, bumping the patch once — grouping changes the *shape*, not the branch/PR/version cadence.

> **Delegate + announce (keeps the main context lean).** From the **top-level command thread**, run substantive work as a **subagent via the Task tool** and **announce it first**: `→ delegating to <agent> because <reason>`. Here the `delivery-tracker` subagent does the decomposition; the main thread orchestrates + reports, so its CLI churn stays in its own context. **No nested delegation** — a subagent does its work *inline*; it cannot spawn further subagents. **Prepend the canonical terse-mode preamble to every subagent prompt** (defined in `commands/deliver.md` §2b — token-economy line; reviewers stay terse but never drop a finding/caveat).

## Steps
1. **Read the board first.** `cd dashboard && python -m backend.cli list`. Reuse an existing Epic/Feature if the work belongs there; never duplicate.
2. **Decompose — delegate to the `delivery-tracker` subagent (announce it).** Print one line first — `→ delegating decomposition to delivery-tracker (owns board structure)` — then invoke it via the Task tool with the exact Feature + atomic US to create. Work → ONE Feature (a capability a stakeholder would name) **grouping several atomic US** → its US. Apply the doctrine — no per-session/umbrella US, no one-US-per-feature fragmentation; if a US would do more than one thing or carry an outsized share of its epic, split it. Give each US `--as-a/--i-want/--so-that` + one `--ac`.
3. **Frame the design — architect co-leads (announce it).** Delegate to the **pertinent designer** (`architect`, or the §2b specialist — `azure-architect`/`dat-architect`/…): `→ delegating design framing to <architect> because the feature has load-bearing decisions`. It states the key decisions + **stubs** the ADR (`docs/adr/NNNN-*.md`) the US build against, so architecture leads development. `delivery-tracker` owns the *board structure*; the architect owns the *design*. **`/fenrir:deliver` then reuses/extends this ADR — it never writes a second one.** **Skip this step** unless the work would route **`full`** per deliver §2 (the `--full` flag, OR the risk-path/large-diff auto-trigger). Light is the default and a docs/config/refactor change gets no architect — same boundary deliver uses, so plan and deliver agree on who gets an architect (no architect-on-everything).
4. **Check granularity.** `python -m backend.cli audit` — fix any US it flags as an umbrella (`coarse_us`, decompose it) and inspect **`thin_features`**: if your new Feature is flagged (an open epic fragmented into single-US features), regroup the US under one Feature before continuing. Atomic-but-expensive US are fine (`expensive_us`).
5. **Commit the planned US to `todo`.** `cli story add` defaults to `backlog` (= a maybe-someday idea); the work you just planned is committed, so move each planned US to **todo**: `python -m backend.cli move --kind story --id <us> --status todo`. Leave only genuine later-ideas in backlog.
6. **Branch.** `git checkout -b feat/<feature-slug>` — one Feature, one branch, one PR.
7. **Print the plan** — the Feature id + its US ids in build order (+ the ADR path) — and STOP. No code at this stage.

## Then
- `/fenrir:deliver` builds the US **one at a time**: `python3 scripts/track_session.py set-us --id <us>` before each, so its real cost lands on that US (Epic = Σ Features = Σ US).
- The PR for this branch delivers the Feature's US; reference them in the PR body so the `delivery-trace` check passes.

## Refuses / degrades
- No `dashboard/` companion app → say board tracking is unavailable here; still create the branch and drop the breakdown into `docs/specs/<feature>.md` so the plan exists somewhere.
- Asked to write code → decline; that is `/fenrir:deliver`. This command plans only.
