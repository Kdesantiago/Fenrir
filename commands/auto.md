---
description: Autonomous end-to-end delivery — chain /fenrir:plan → /fenrir:deliver → /fenrir:ship for one feature, with a checkpoint per stage, STOPPING on any gate/validation failure, and NEVER merging (the human merge is the terminal step, by design). Use to drive a reasonably-scoped feature from intent to an open, green PR with minimal hand-holding. NOT for a fuzzy idea (run /fenrir:challenge-me first) and NOT a way to bypass review — it prepares the PR; branch-protection + a human decide the merge.
---

# /fenrir:auto — autonomous plan→deliver→ship (stops at the human gate)

Run the whole golden path for ONE feature without step-by-step prompting — but **automate the chores, never the judgment.** This command removes manual hand-offs between plan/deliver/ship; it does **not** remove the human merge gate, and it **stops** the moment anything fails rather than pushing through.

`$ARGUMENTS` = the feature/task to deliver. Empty → ask what to build, then stop.

## The one hard rule
**It NEVER merges.** The terminal state is an open PR with green CI awaiting a human. Auto-merge would delete the judgment couche-0 exists to protect (see GETTING-STARTED §5). If you find yourself about to `gh pr merge`, STOP — that is not this command's job.

## Pipeline (each stage is a checkpoint; a failure STOPS the chain)
Record a one-line ledger row per stage in the spec artifact (`docs/specs/<slug>.md`, rows `plan | deliver | ship | status | ref`) so a re-run of `/fenrir:auto` reads it and resumes from the first non-passed stage, not the start. (deliver keeps its own per-US sub-ledger in the same file.)

1. **Scope guard (testable, not vibes).** To proceed you MUST be able to state, in one line each: a **steelman** of the change and a **single crisp acceptance criterion**. If you cannot → STOP and route to `/fenrir:challenge-me` (don't auto-build an unscoped idea — an autonomous chain must not rationalize "clear enough"). Also confirm the gate is actually armed (`python scripts/bootstrap_smoke_test.py`); if branch-protection isn't applied, WARN that the terminal PR is mergeable without enforcement (the "infra decides the merge" guarantee is hollow until the gate is armed — `python scripts/bootstrap.py` for the in-session hooks + `python scripts/set_branch_protection.py --repo OWNER/REPO` for branch-protection, no `terraform`/`gh` required). No `org-profile.yaml` → route to `repo-bootstrap` first.
2. **`/fenrir:plan`.** Decompose into a Feature + atomic US (delivery-tracker), architect frames the ADR, branch created — per plan's own contract. Announce the delegations. **Then announce the blast radius:** "N US ≈ ~M subagent runs, unattended" — and if **N > 6 US**, require a human ack before entering the deliver loop (a large autonomous spend must be opt-in). STOP if no coherent plan emerges (the idea isn't ready).
3. **`/fenrir:deliver`.** Build the US **one at a time** (set-us → build → commit per US), routing each to the pertinent specialist/generator, with deliver's route-appropriate validation gate at the end. **`/fenrir:auto` adds nothing to deliver's gate — it inherits deliver's failure-handling contract whole:** on any deliver hard-failure, **STOP, do not ship**; deliver's bounded re-validation (its own ceiling) applies and `/fenrir:auto` adds no loop of its own. Do not re-state deliver's failure list here — whatever deliver treats as a hard failure, auto stops on.
4. **`/fenrir:ship` — PR-open behavior ONLY.** Run ship's PR-build + CI-status surfacing. **Do NOT execute ship's post-merge behavior (the squash-merge / branch-delete / US→`done` block)** — that runs only *after a human merges*, never from `/fenrir:auto`. Ship opens the PR; it does not merge it here.
5. **Terminal: await human.** Report the open PR + per-US cost. CI is usually **pending** right after ship — **report it pending and STOP; do NOT poll/wait for green** (that's the human's checkpoint). If already red, STOP with the failing check — never retry blindly, never re-plan to "fix" it.

## Stop conditions (any → halt, report, leave checkpoints for resume)
- Fuzzy scope / no crisp acceptance criterion (→ challenge-me); no coherent plan; **any `/fenrir:deliver` hard-failure** (deliver defines them — auto does not duplicate the list); red CI.
- A deliver hard-fail **STOPS the chain — never re-invoke `/fenrir:plan` to "fix" the decomposition** (that's a re-plan loop). Re-validation is deliver's own; `/fenrir:auto` adds no loop of its own.
- **Never** proceed past a failed gate, and **never** merge or poll-wait for CI.
- No `org-profile.yaml` → route to `repo-bootstrap` first.

## What it is / isn't
- **Is:** the manual chores between plan/deliver/ship, automated, with the same gates each command already enforces and a checkpointed, resumable chain.
- **Isn't:** an auto-merger, a way to skip qa/red-team, or a license to build an unscoped idea. The gate (CI + branch-protection) and the human still decide the merge — `/fenrir:auto` just gets you to that decision with a green, reviewed PR.

## Output
The Feature + US ids, the ADR/spec paths, what ran at each stage, the open PR URL + CI status, and the per-US cost. Plus the explicit line: **merge is the human's call — this command stopped at the gate.**
