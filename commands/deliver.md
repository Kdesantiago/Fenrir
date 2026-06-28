---
description: Orchestrate the full delivery pipeline (architect → coder → qa-tester → reviewer → delivery-gates → PR) adaptively, routing light vs full by a deterministic diff/risk computation, with a disk spec artifact as ground truth and a git checkpoint per stage.
---

# /fenrir:deliver

Orchestrate a change from intent to a ready-to-open PR. Routing and gating are **deterministic** (computed by shell/git), never an LLM vibe. Every subagent has ISOLATED context, so the **spec artifact on disk is the single source of truth** they each re-read. This command does NOT enforce merge — the real gate is CI required-checks + branch-protection (infra). It prepares the PR; infra decides if it merges.

## 0. Preconditions
- Confirm `org-profile.yaml` exists at repo root and a clean-enough working tree. If no profile, STOP and route to `repo-bootstrap`.
- **Plan-first (board breakdown).** Check this work has a **Feature + atomic US** on the board (`cd dashboard && python -m backend.cli list`). If none covers the task, create it now — run `/fenrir:plan` (or delegate to `delivery-tracker`) to decompose into one Feature + atomic US **before** building. Strong default, advisory: auto-create the plan, don't hard-block (the real gate is the `delivery-trace` CI check — the PR must reference a US). One Feature = one branch = one PR. Then build the US **one at a time**: `python3 scripts/track_session.py set-us --id <us>` before each US's work so its real cost lands on that US (Epic = Σ Features = Σ US).
- Resolve the default branch robustly (fresh CI checkouts often have `origin/HEAD` unset):
  ```sh
  DEF=$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  DEF=${DEF:-$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p')}
  DEF=${DEF:-main}
  BASE=$(git merge-base HEAD "origin/$DEF" 2>/dev/null || git rev-parse "origin/$DEF" 2>/dev/null)
  [ -z "$BASE" ] && { echo "cannot resolve base branch; aborting routing"; exit 1; }
  ```

## 1. Write the SPEC ARTIFACT first (anti context-loss)
Before any subagent runs, write `docs/specs/<slug>.md` (slug = kebab of the task). It is the contract every downstream agent reads. Include:
- **Goal / acceptance criteria**, **scope / out-of-scope**, **affected paths**, **profile keys in play**, and a **stage ledger** (table: stage | status | checkpoint ref | artifact path) that you update as the pipeline runs.
Pass each subagent the **path** to this file, not a prose summary. Architect's ADR and qa-tester's tests link back to it.

## 2. DETERMINISTIC routing (script, not judgment)
Compute, with git/shell — do not eyeball:
```sh
FILES=$(git diff --name-only "$BASE"...HEAD | wc -l | tr -d ' ')
# No bc; awk sums and defaults to 0 when a diff is single-sided (insertions OR deletions only).
LOC=$(git diff --shortstat "$BASE"...HEAD | grep -oE '[0-9]+ (insertion|deletion)' | grep -oE '^[0-9]+' | awk '{s+=$1} END{print s+0}')
# Match risk paths at ANY depth — the monorepo nests them (src/<svc>/auth/...), so do not anchor with ^.
RISK=$(git diff --name-only "$BASE"...HEAD | grep -Ec '(^|/)(auth|iac|migrations|security)/')
```
For a not-yet-coded feature with no diff, derive FILES/LOC/RISK from the spec's affected-paths instead, using the same globs.

**Route by rule:**
- **`light` (hotfix)** when `RISK == 0` AND `FILES <= 5` AND `LOC <= 80`.
  Pipeline: **coder → delivery-gates → ship**. (No architect/qa-tester/reviewer overhead.)
- **`full` (feature)** otherwise — any risk-path hit, OR larger diff.
  Pipeline: **architect → coder → qa-tester → reviewer → delivery-gates → ship**.

Record the chosen route + the three numbers in the spec ledger. Routing is reproducible: same diff → same route.

## 3. Run the pipeline with a CHECKPOINT per stage
Work on a dedicated branch: `git switch -c deliver/<slug>` (or reuse if resuming).
Before each stage, snapshot: commit WIP or `git stash push -m "deliver:<slug>:<stage>"`, and record the ref in the ledger.

- **architect** (full only): reads spec → writes `docs/adr/NNNN-*.md`, sets the decision the coder builds against.
- **red-team** (full + risk-path diffs only): `red-team-destroyer` attacks the ADR before any code is written. Parse its final `VERDICT:` line — `REDESIGN` is treated like reviewer=BLOCK (STOP, loop back to architect); `FIX-FIRST` means fold its findings into the spec before coding; `SHIP` proceeds.
- **coder**: delegate to the **`coder` subagent** to implement against the spec + ADR. Running it as a subagent means its token spend lands in `toolUseResult` and is attributable to the US (see §6). It returns files touched + what it ran.
- **qa-tester** (full only): reads spec/ADR → writes new tests + any bug repro; must run them and report real results.
- **doc-keeper** (both): syncs `CHANGELOG.md` + affected README(s)/API-docs to the diff BEFORE review (so the changelog entry reviewer checks for already exists). Idempotent.
- **native correctness review** (full only): run `/code-review` **from this command body** (the main thread can use SlashCommand; a subagent cannot). Capture its findings as text.
- **reviewer** (full only): pass it the captured `/code-review` findings + the diff → it adds org PR-hygiene (conventional title, ADR link, changelog, profile) and returns a single advisory merge-ready verdict. It does NOT re-run `/code-review` itself.
- **delivery-gates** (both): lint/type/test/coverage on the diff for fast local feedback. Advisory.

## 4. Failure handling — STOP, do not open a PR
- **Hard failure** (a stage errors, gates fail, reviewer verdict = BLOCK, red-team verdict = REDESIGN, qa repro still failing): STOP immediately. Do NOT proceed to ship/PR. Record the failing stage + checkpoint ref in the ledger and report.
- **Resume**: re-invoking `/fenrir:deliver` reads the ledger, restores the last good checkpoint, and re-enters at the first non-passed stage — earlier passed stages are not redone.

## 5. Hand off to ship (only if every stage passed)
Invoke `/fenrir:ship` to open the PR. Pass it the spec path and the ADR path so they're linked in the PR body.

## 6. Cost & US tracking (when the `dashboard/` board exists)
Standardize the work as a tracked, costed **User Story** (the `us-cost-tracking` skill):
- **Before the pipeline:** represent the task on the board — one **User Story** (under an
  Epic → Feature) mirroring this spec's goal — and move it to `in_progress`
  (`python -m backend.cli story add … ` / `move --kind story --id us-N --status in_progress`).
  One spec = one US, so cost and review map 1:1 to a board item.
- **After the run (or per stage):** attribute the **real** spend to that US —
  `python -m backend.cli link --kind story --id us-N --session <session-id>` (idempotent per
  session+US; writes one entry per source — main vs subagent — so the coder/qa/reviewer
  subagent cost is captured). On success move the US to `review`/`done`.
- **Report** the US cost with `cli trace --us us-N`; subagent breakdown via the dashboard
  Subagents view. Cost is a derived estimate, never a gate.
This is advisory bookkeeping, not a merge gate — couche-0 (CI + branch-protection) gates.

## Stop conditions
- No `org-profile.yaml` → route to `repo-bootstrap`, stop.
- Any hard failure → stop before PR, leave checkpoints intact for resume.
- This command never claims the merge is gated by it; CI + branch-protection do that.
