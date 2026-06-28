---
description: Orchestrate the full delivery pipeline adaptively — route the design/build to the PERTINENT specialist agent by request type (azure-architect, dat-architect, api-first, data-model, iac-gen…; generic architect/coder only as fallback), with a MANDATORY qa-tester + red-team-destroyer validation gate at the end of EVERY route, a disk spec artifact as ground truth, and a git checkpoint per stage. Light vs full (diff/risk-computed) only changes design/review overhead, never whether the change is validated.
---

# /fenrir:deliver

Orchestrate a change from intent to a ready-to-open PR. **Route selection** (light vs full) is **deterministic** (computed by shell/git, never an LLM vibe); the **validation-gate verdict** (qa + red-team) is an LLM judgment, advisory-with-stop. Every subagent has ISOLATED context, so the **spec artifact on disk is the single source of truth** they each re-read. This command does NOT enforce merge — the real gate is CI required-checks + branch-protection (infra). It prepares the PR; infra decides if it merges.

## 0. Preconditions
- Confirm `org-profile.yaml` exists at repo root and a clean-enough working tree. If no profile, STOP and route to `repo-bootstrap`.
- **Plan-first (board breakdown).** Check this work has a **Feature + atomic US** on the board (`cd dashboard && python -m backend.cli list`). If none covers the task, create it now — run `/fenrir:plan` (or delegate to `delivery-tracker`) to decompose into one Feature + atomic US **before** building. Strong default, advisory: auto-create the plan, don't hard-block (the real gate is the `delivery-trace` CI check — the PR must reference a US). One Feature = one branch = one PR. Then build the US **strictly one at a time** — this is what makes per-US cost real: **`set-us <us>` → build ONLY that US → `git commit` (referencing that us-N) → next US**. Do **NOT batch several US under one `set-us` window**: cost is time-swept to whichever US was active, so siblings built in the same window land at **$0** while the window's US absorbs the lot. One `set-us` per US (a commit per US where practical) bounds each US's cost window so the sweep can split it. **Move each US as you go** — `cli move --kind story --id <us> --status in_progress` when you start it (so the board visibly advances), `--status review` when its slice is PR-ready. (`/fenrir:ship` moves them to `done` after merge.) Pin `FENRIR_DASH_BOARD` (or run the CLI from the repo root) so the board always resolves to this repo, never a subdir.
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
  Pipeline: **(specialist) coder → qa-tester → red-team-destroyer → delivery-gates → ship**. (Skips the architect/ADR + reviewer-hygiene overhead — but NOT validation.)
- **`full` (feature)** otherwise — any risk-path hit, OR larger diff.
  Pipeline: **(specialist) architect → coder → qa-tester → /code-review → reviewer → red-team-destroyer → delivery-gates → ship**.

**The QA + red-team validation at the end runs on BOTH routes** — `qa-tester` then `red-team-destroyer` review the *actual change* before ship. Routing decides the *design/review* overhead (architect, ADR, hygiene reviewer), never whether the change is looked at. Two right-sizing rules so this doesn't gut `light`:
- **Proportionality (`light` only):** when the change is **≤20 LOC or has no executable lines** (typo / version bump / comment / docs / config), `qa-tester` is **skipped** and `red-team-destroyer` runs **advisory** (log its verdict, do NOT stop). A `light` change with real logic gets the full blocking gate.
- **Severity threshold:** only **critical/high** findings (or a `REDESIGN`/`FIX-FIRST` driven by them) block; medium/low from any reviewer are advisory.

**Route selection (light/full) is deterministic** (the shell numbers above — same diff → same route). The validation-gate *verdict* is an LLM judgment, intentionally advisory-with-stop, not a deterministic computation. Record the chosen route + the three numbers in the spec ledger.

## 2b. Pick the SPECIALIST agent (by request type — default, not opt-in)
Specialized subagents are the **default** for Fenrir commands: route the design/build stages to the *pertinent* specialist instead of always the generic `architect`/`coder`. Decide from the request + the spec's affected paths + `org-profile.yaml`:

| The work is about… | Design/build via |
|---|---|
| Azure infra/sizing/region/SKU decision | `azure-architect` (ADR) → `iac-gen` |
| A full technical-architecture doc | `dat-architect` |
| An API contract / endpoint | `api-first` |
| DB schema / query / index | `data-model` → `db-migration` |
| IaC / Helm / App Service | `iac-gen` (via `stack-adapter` if `stack-interface.yaml`) |
| Auth / OIDC wiring | `auth-gen` |
| Observability / SLO / alerts | `observability-gen` |
| LLM client / RAG / LangGraph | `llm-gen` / `retriever` / `langgraph-workflow` |
| Context-window / prompt design | `context-engineering` |
| Live Azure incident / cost / WAF | `azure-sre` / `azure-cost` / `azure-waf` |
| Frontend / UI component or page | `frontend-gen` |
| Scheduled / recurring job | `cronjob` |
| Security review / hardening of a diff | `security-review` (skill) / `security-guardrail` |
| Refactor / simplify — no behavior change | `coder` directly (no architect/ADR) |
| Docs / config / process / prompt-only change | no architect — `coder` or a direct edit; `qa-tester` skipped (§3) |
| Generic app feature / fix, no specialist fits | `architect` (full) → `coder` |

Record the chosen specialist in the spec ledger. The generic `architect`/`coder` is the **fallback** for a genuine feature with no matching specialist — when **no row matches at all, route to plain `coder`, do NOT force-fit a specialist**. (A docs/config/refactor change routed `light` by §2 must NOT be dragged into the full architect pipeline by this table — the §2 route wins.)

**Announce + delegate (transparency + lean context).** Before each delegation, print one line in the thread — `→ delegating to <agent> because <reason>` — so the routing is visible, not guessed. **Delegation is route-aware, not unconditional:**
- **`full` route:** run each stage as a subagent via the Task tool (architect, coder/generator, qa-tester, reviewer, red-team-destroyer) — the main thread only orchestrates, parses verdicts, and reports, so each subagent's tool churn stays in its own context and the main window doesn't fill (context pressure compounds when auto-compaction hasn't fired).
- **`light` route / §2 proportional change:** do NOT force a subagent per stage — a 1-line/typo/docs fix shouldn't spawn coder+qa+red-team. Edit inline; honor §2 (qa skipped, red-team advisory) — the validation still *runs*, just right-sized.
- **No nested delegation:** a subagent does its assigned work **inline** — it cannot spawn further subagents (no Task tool inside a subagent). Only the top-level command thread delegates.
- **Token economy — every delegated subagent runs TERSE.** Prepend this line to EVERY subagent prompt: *"⚡ Respond in caveman/terse mode (token economy): drop articles, filler, pleasantries, hedging; fragments OK; keep ALL technical substance, exact `file:line`, code, and your VERDICT. Minimise output tokens."* The subagent's reply is what re-enters the (paid) main context, so terse replies cut cost on every delegation — keep its *thinking* full, just its *output* lean. **Verdict-bearing reviewers (`qa-tester`, `red-team-destroyer`, `reviewer`) stay terse in PROSE but must NEVER drop a finding, caveat, or severity** — economy must not cost a real signal.

## 3. Run the pipeline with a CHECKPOINT per stage
Work on a dedicated branch: `git switch -c deliver/<slug>` (or reuse if resuming).
Before each stage, snapshot: commit WIP or `git stash push -m "deliver:<slug>:<stage>"`, and record the ref in the ledger.

- **architect / specialist** (full only): the §2b specialist (or generic `architect`) reads spec → writes `docs/adr/NNNN-*.md`, sets the decision the build stage implements against.
- **ADR red-team** — ledger stage `adr-redteam` (full + risk-path diffs only): `red-team-destroyer` attacks the **ADR** *before* code is written; its verdict line must name the stage (`VERDICT(adr): …`). `REDESIGN` = STOP, loop to architect; `FIX-FIRST` = fold into the spec before coding; `SHIP` proceeds. Distinct from the final `diff-redteam` below (different artifact, different ledger entry — resume can tell them apart).
- **coder / specialist generator**: delegate to the §2b build agent (the `coder` subagent, or the matching generator skill) to implement against the spec + ADR. Running it as a subagent means its token spend lands in `toolUseResult` and is attributable to the US (see §6). It returns files touched + what it ran.
- **doc-keeper** (both): syncs `CHANGELOG.md` + affected README(s)/API-docs to the diff BEFORE review (so the changelog entry reviewer checks for already exists). Idempotent.
- **native correctness review** (full only): run `/code-review` **from this command body** (the main thread can use SlashCommand; a subagent cannot). Capture its findings as text.
- **reviewer** (full only): pass it the captured `/code-review` findings + the diff → it adds org PR-hygiene (conventional title, ADR link, changelog, profile) and returns a single advisory merge-ready verdict. It does NOT re-run `/code-review` itself.

### Validation gate — runs LAST before ship (right-sized per §2)
- **qa-tester** — ledger stage `qa` (both routes, unless skipped by §2 proportionality): writes new tests + any bug repro for the change and runs them. **Pass criterion:** the *new-coverage* tests are green AND any bug-repro **passes after the fix** — a repro that fails *before* the fix is qa's expected output, NOT a gate failure. Report real results.
- **diff red-team** — ledger stage `diff-redteam` (both routes; advisory-only on a `light` proportional change): `red-team-destroyer` adversarially reviews the **actual diff** — every bug, footgun, data-loss path, gate weakening; verdict line names the stage (`VERDICT(diff): …`). A `REDESIGN`/`FIX-FIRST` driven by **critical/high** findings is a hard failure (STOP per §4); medium/low are advisory; `SHIP` proceeds.
- **delivery-gates** (both): lint/type/test/coverage on the diff for fast local feedback. Advisory.

## 4. Failure handling — STOP, do not open a PR
- **Hard failure** (a stage errors, gates fail, reviewer = BLOCK, either red-team — `adr-redteam` or `diff-redteam` — returns `REDESIGN`/`FIX-FIRST` on **critical/high** findings, or `qa`'s new-coverage tests are red / a repro still fails after the fix): STOP immediately. Do NOT ship/PR. Record the failing stage + checkpoint ref and report. A `FIX-FIRST` means fold the fixes in and re-validate, not ship-anyway.
- **Bounded re-validation (no infinite loop).** Re-validate at most **twice**; on a 3rd non-`SHIP`, STOP and hand the findings to a human — do not keep looping (the red-team's mandate guarantees it can always find *something*; only critical/high may block, medium/low are advisory). The loop has a hard ceiling.
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
