---
description: Orchestrate delivery adaptively — light by DEFAULT (inline edit, or one specialist subagent for real-logic changes), with the full multi-agent pipeline (architect→coder→qa→reviewer→red-team) OPT-IN via `--full` or auto-triggered only for risky/large diffs (auth/iac/migrations/security, or over the size threshold). Routes the design/build to the PERTINENT specialist by request type (azure-architect, dat-architect, api-first, data-model, iac-gen…). Validation is always run, right-sized per route: the full route AND any light change touching REAL LOGIC get the MANDATORY blocking qa-tester + red-team-destroyer gate; only a genuinely TRIVIAL light change (typo/comment/docs/config, tiny diff) ships gateless. Disk spec artifact is ground truth; git checkpoint per stage.
---

# /fenrir:deliver

Orchestrate a change from intent to a ready-to-open PR. **Default route is `light`** — a solo dev's trivial edit must NOT spawn six subagents; the full multi-agent pipeline is **opt-in** (§2). **Route selection** is **deterministic** (computed by shell/git, never an LLM vibe); the **validation-gate verdict** (qa + red-team) is an LLM judgment that BLOCKS on the full route and on any real-logic light change (advisory-only for a trivial light change). Every subagent has ISOLATED context, so the **spec artifact on disk is the single source of truth** they each re-read. This command does NOT enforce merge — the real gate is CI required-checks + branch-protection (infra). It prepares the PR; infra decides if it merges.

## 0. Preconditions
- Confirm `org-profile.yaml` exists at repo root and a clean-enough working tree. If no profile, STOP and route to `repo-bootstrap`.
- **Plan-first (board breakdown).** Check this work has a **Feature + atomic US** on the board (`cd dashboard && python -m backend.cli list`). If none covers the task, create it — run `/fenrir:plan` (or delegate to `delivery-tracker`) **before** building. Strong default, advisory (don't hard-block; the real gate is the `delivery-trace` CI check — the PR must reference a US). One Feature = one branch = one PR. Then build the US **strictly one at a time**: **`set-us <us>` → build ONLY that US → `git commit` (referencing us-N) → next US**, one `set-us` per US — do NOT batch several US in one window. *Why one-at-a-time matters (cost is time-swept; batched siblings land at $0) + the US move/link mechanics: `skills/us-cost-tracking/SKILL.md` + the `delivery-tracker` agent; §6 below.* Pin `FENRIR_DASH_BOARD` (or run the CLI from repo root) so the board resolves to this repo.
- Resolve the default branch robustly (fresh CI checkouts often have `origin/HEAD` unset):
  ```sh
  DEF=$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  DEF=${DEF:-$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p')}
  DEF=${DEF:-main}
  BASE=$(git merge-base HEAD "origin/$DEF" 2>/dev/null || git rev-parse "origin/$DEF" 2>/dev/null)
  [ -z "$BASE" ] && { echo "cannot resolve base branch; aborting routing"; exit 1; }
  ```

## 1. Write the SPEC ARTIFACT first (anti context-loss)
Before any subagent runs, write `docs/specs/<slug>.md` (slug = kebab of the task) — the contract every downstream agent reads. Include **goal / acceptance criteria**, **scope / out-of-scope**, **affected paths**, **profile keys in play**, and a **stage ledger** (table: stage | status | checkpoint ref | artifact path) you update as the pipeline runs. Pass each subagent the **path**, not a prose summary; the ADR and qa's tests link back to it.

## 2. DETERMINISTIC routing — `light` is the DEFAULT, `full` is opt-in
**Default = `light`.** A solo dev's trivial edit must NOT spawn six subagents. The full multi-agent pipeline (architect → coder → qa → reviewer → red-team) runs ONLY when **explicitly forced** (`--full` flag) OR **auto-triggered** for a genuinely risky/large diff. Compute the trigger with git/shell — do not eyeball:
```sh
FILES=$(git diff --name-only "$BASE"...HEAD | wc -l | tr -d ' ')
# No bc; awk sums and defaults to 0 when a diff is single-sided (insertions OR deletions only).
LOC=$(git diff --shortstat "$BASE"...HEAD | grep -oE '[0-9]+ (insertion|deletion)' | grep -oE '^[0-9]+' | awk '{s+=$1} END{print s+0}')
# Match risk paths at ANY depth — the monorepo nests them (src/<svc>/auth/...), so do not anchor with ^.
RISK=$(git diff --name-only "$BASE"...HEAD | grep -Ec '(^|/)(auth|iac|migrations|security)/')
```
For a not-yet-coded feature with no diff, derive FILES/LOC/RISK from the spec's affected-paths using the same globs.

**Route by rule:**
- **`full`** when the user passed **`--full`**, OR auto-triggered when `RISK >= 1` (diff touches `auth/`, `iac/`, `migrations/`, or `security/`) OR `FILES > 5` OR `LOC > 80`.
  Pipeline: **(specialist) architect → coder → qa-tester → /code-review → reviewer → red-team-destroyer → delivery-gates → ship**.
- **`light` (default)** otherwise — no risk-path hit, small diff, no `--full`.
  Pipeline: **(specialist) coder OR a direct inline edit → lightweight review → delivery-gates → ship**. Skips the architect/ADR + the hygiene reviewer. **Branches on REAL LOGIC vs TRIVIAL (below):** a real-logic light change gets the MANDATORY blocking qa+red-team gate; a trivial one gets only an advisory glance.

**What counts as REAL LOGIC vs TRIVIAL (the light-route fork — make this call explicitly and record it in the ledger):**
- **TRIVIAL** = *no real logic touched*: a change confined to comments / docs / prose (`*.md`), a version/dependency bump, a string/constant/copy tweak, formatting/whitespace, or **config-only** data (`*.yaml`/`*.toml`/`*.json`/`.env`) with **no behavioral branch** — AND the diff is tiny (**≤20 LOC and no new/changed executable statements**: no added/edited conditionals, loops, calls, error handling, arithmetic, I/O, query, or control flow). If *any* executable line changes, it is **NOT** trivial.
- **REAL LOGIC** = anything that changes program behavior: an added/edited function or branch, a new/changed call, a condition, a loop, error handling, data transformation, a query, parsing, a regex, I/O, or a config value the code reads to **decide** something. When in doubt, it is real logic (fail safe toward the gate).

**Validation, right-sized per route — never skipped, but proportional:**
- **`full` route — MANDATORY blocking gate:** `qa-tester` then `red-team-destroyer` review the *actual change* before ship. Blocks on **critical/high** findings (medium/low advisory). Non-negotiable on `full`.
- **`light` route + REAL LOGIC — MANDATORY blocking gate:** run the qa+red-team verification pass — `qa-tester` writes/runs the new-coverage tests, then `red-team-destroyer` adversarially reviews the diff — and it is **blocking on ANY confirmed finding** (not only critical/high). This is the **qa + red-team verification pass only**, NOT the full architect→coder→reviewer pipeline (that stays `--full`/auto-risk). The chosen §2c specialist runs first, then this gate validates its output.
- **`light` route + TRIVIAL — NO blocking gate (the token win):** skip `qa-tester`; run `red-team-destroyer` **advisory** (log verdict, do NOT stop). A genuinely trivial change ships without a gate.
- **Severity threshold:** on `full` and on the trivial-light advisory pass, only **critical/high** findings block (medium/low advisory). On the **real-logic light gate**, **any confirmed finding blocks** (the deliberately stricter contract — a small real-logic change with no architect/reviewer in front of it earns a hard qa+red-team gate).

**Forcing full:** `--full` is the manual override for a small-but-load-bearing change you want architect-framed and hard-gated; the auto-trigger handles the risky/large case. **Route selection is deterministic** (flag + shell numbers → same input, same route); the validation *verdict* is an LLM judgment. Record route + `--full`? + the three numbers in the spec ledger.

## 2c. DETERMINISTIC specialist router (glob + change-kind → ONE specialist, zero LLM tokens on the common path)
*Implements ADR 0006.* After §2 fixes the **route** (`light`/`full`), this step fixes the **build agent** — *which* specialist runs the build stage. It is **orthogonal to** §2: picking `api-coder` over generic `coder` does **NOT** promote a `light` change to `full`; the §2 light-default + full-opt-in/auto-risk logic is untouched. Four ordered tiers, **first match wins**:

### Tier 0 — explicit override
If the user named a specialist (`--agent=<name>`) or the spec ledger pins one, use it. Skip classification. Record `route_classification: deterministic`.

### Tier 1 — DETERMINISTIC dispatch (glob + change-kind → specialist), zero LLM tokens
Compute the changed paths once (`git diff --name-only "$BASE"...HEAD`, or the spec's affected-paths for a not-yet-coded change), then match each against the table **top-to-bottom; the first row that matches any changed path wins**. **Risk-path rows (1-4) are ordered first** so a security/auth/migration change never falls through to a weaker specialist. Globs match at **any depth** — anchor with `(^|/)` (never a bare `^`), the monorepo nests `src/<svc>/…`.

**Dispatch table — glob / change-kind → specialist (realized-by per ADR 0002: a skill body read by a `coder` subagent, or a real agent; generic `coder` is the only fallback):**

| # | Path glob (any depth, `(^\|/)`-anchored) | Change-kind signal | Specialist slot | Realized by |
|---|---|---|---|---|
| 1 | `(^\|/)auth/`, `(^\|/)oidc/`, `(^\|/)login/` | authn/authz, token, session, guard | **auth-coder** | `auth-gen` skill |
| 2 | `(^\|/)security/`, `(^\|/)crypto/`; files matching `*sanitiz*`,`*secret*` | injection/XSS/CSRF/SSRF, secret handling | **security-coder** | `security-review` skill + `security-guardrail` |
| 3 | `(^\|/)migrations/`, `(^\|/)alembic/`, `(^\|/)versions/.*\.py` | schema migration / backfill | **migration-coder** | `db-migration` skill |
| 4 | `(^\|/)iac/`, `(^\|/)helm/`, `(^\|/)charts/`, `.*\.tf$`, `.*\.bicep$` | infra / Helm / App Service | **iac-coder** | `iac-gen` (+ `stack-adapter` if `stack-interface.yaml`) |
| 5 | `.*_test\.py$`, `(^\|/)tests/`, `(^\|/)test_.*\.py$`, `.*\.spec\..*` | test-only diff | **testing-coder** | `qa-tester` agent |
| 6 | `(^\|/)resilience/` | timeout / retry / circuit-breaker / idempotency | **resilience-coder** | **`resilience` skill** (NEW) |
| 7 | `(^\|/)src/[^/]+/api/`, `(^\|/)routers/`, `(^\|/)endpoints/`, `(^\|/)openapi.*\.ya?ml` | HTTP endpoint / contract | **api-coder** | `api-first` skill |
| 8 | `(^\|/)src/[^/]+/schemas/`, `(^\|/)schemas/`, `(^\|/)dto/` | DTO / request-response schema / validation model | **schema-coder** | **`dto-schemas` skill** (NEW) |
| 9 | `(^\|/)models/`, `(^\|/)repositories/`, `(^\|/)queries/` (no `migrations/`) | ORM model / query / index | **data-access-coder** | `data-model` skill |
| 10 | `(^\|/)src/[^/]+/core/settings.*`, `(^\|/)config/`, `.*settings.*\.py$`, `(^\|/)\.env` | typed config / feature-flag | **config-coder** | **`app-config` skill** (NEW; + `feature-flags`/`secrets` skill) |
| 11 | `(^\|/)src/[^/]+/services/` (not already matched by rows 1-2, 6-9) | domain service / business orchestration | **domain-services-coder** | **`domain-services` skill** (NEW) |
| 12 | `(^\|/)observability/`, `(^\|/)telemetry/`, `(^\|/)logging/` | OTel / SLO / alerts | **observability-coder** | `observability-gen` skill |
| 13 | front globs per profile (`.*\.tsx$`,`.*\.vue$`,`.*\.svelte$`, streamlit `(^\|/)pages/`) | UI component / page / a11y | **frontend-coder** | `frontend-gen` skill |
| 14 | `(^\|/)llm/`, `(^\|/)prompts/`, `(^\|/)agents/` (app graph, not Fenrir `agents/`) | LLM client / RAG / graph | **llm-coder** | `llm-gen` / `retriever` / `langgraph-workflow` |
| 15 | `(^\|/)consumers/`, `(^\|/)producers/`, `(^\|/)messaging/` | queue / topic / DLQ | **messaging-coder** | `event-driven` skill |
| 16 | `(^\|/)jobs/`, `(^\|/)cron/`, `(^\|/)schedulers/` | scheduled / recurring job | **jobs-coder** | `cronjob` skill |
| 17 | `.*\.md$`, `(^\|/)docs/`, `(^\|/)CHANGELOG`, config-only `.*\.(ya?ml\|toml)$` | docs / config / prose | **docs-coder** | `doc-keeper` agent (no architect; §2 light route wins) |
| 18 | `(^\|/)async/`, `(^\|/)concurrency/` | async/await, threading, lock, race, cancellation | **concurrency-coder** | **`concurrency` skill** (NEW) |
| 19 | `(^\|/)clients/`, `(^\|/)integrations/`, `(^\|/)webhooks/` | third-party client / SDK / webhook | **integration-coder** | **`integration-client` skill** (NEW) |
| 20 | `(^\|/)storage/`, `(^\|/)uploads/`, `(^\|/)files/` | file / blob / object upload / stream | **storage-coder** | **`file-storage` skill** (NEW) |
| 21 | `(^\|/)cli/`, `(^\|/)cli\.py`, `(^\|/)cmd/`, `(^\|/)__main__.py`, console_scripts entry-point | argparse / click / typer / subcommand | **cli-coder** | **`cli` skill** (NEW) |
| 22 | `(^\|/)cache/`, `(^\|/)caching/` | cache / TTL / invalidation | **caching-coder** | `caching` skill |
| 23 | `(^\|/)ws/`, `(^\|/)websocket`, `(^\|/)sse/`, `(^\|/)realtime/` | websocket / SSE / stream | **realtime-coder** | `realtime-transport` skill |
| 24 | `(^\|/)search/`, `(^\|/)retrieval/` | full-text / vector / recall | **search-coder** | `retriever` skill |
| 25 | `(^\|/)kb/`, `(^\|/)knowledge/` | ingest / dedup / freshness / citation | **kb-coder** | `knowledge-base` skill |
| — | anything else | general business logic | **(fallback)** | generic `coder` |

> **Row 11 ordering note.** `domain-services` (`src/<svc>/services/`) sits **below** auth (1), security (2), resilience (6), api (7), schema (8), data-access (9) so a service file that is *really* an auth/security/api/schema/data concern is claimed by the stronger, more specific specialist first; only a service with no such stronger signal lands on `domain-services-coder`.

**Discipline — ONE specialist per atomic change.** The router returns **exactly one** specialist. If multiple rows match (e.g. a change spanning `api/` + `models/`), it does **NOT** fan out to two specialists (token blowout + split context): it picks the **single highest-priority row** (lowest #; risk rows 1-4 dominate) and passes the *other* concern as a **note in the receipt** for a follow-up US. A genuinely **cross-cutting** change that one specialist cannot serve is exactly the signal to **escalate to `--full`** (architect frames the split into per-concern US) — never to spawn a swarm.

### Tier 2 — single cheap LLM classification (ambiguity ONLY)
Invoke the model to classify **only** when Tier 1 is genuinely ambiguous: (a) **no row matched** but the change is non-trivial app logic, or (b) two equal-priority risk rows matched different files and the atomic-change rule can't disambiguate by priority. This is **ONE** classification call, output constrained to a single specialist name from the table (or `coder`) — NOT a design step, NOT per-file. Record `route_classification: llm`.

### Tier 3 — generic coder fallback
No row matched and Tier 2 returns no specialist → route to generic `coder` (ADR 0002's deliberate home for open-ended backend logic). Never force-fit a specialist.

**Ledger field.** Record `route_classification: deterministic | llm` (deterministic for Tier 0/1, llm for Tier 2) in the per-US ledger/receipt alongside the chosen specialist, so the LLM path is auditable and stays rare.

**Gate stays OPT-IN.** Risk-path rows (1-4) coincide with §2's `RISK` globs, so a security/auth/migration change is *already* auto-`full` by §2 — the router just names the right hands inside that gate. On a `light` route the chosen specialist runs as the **one** subagent (or inline for a trivial change), honoring §2's right-sized validation.

## 2b. Pick the SPECIALIST agent — see §2c's deterministic tiers
Specialized subagents are the **default** for Fenrir commands: the design/build stages route to the *pertinent* specialist instead of always the generic `architect`/`coder`. **The routing decision is owned by §2c** (Tier 0 explicit `--agent` → Tier 1 glob+change-kind dispatch → Tier 2 single cheap LLM classify on ambiguity → Tier 3 generic `coder`). Do **not** duplicate a prose routing table here — apply §2c, then map the chosen specialist slot to its design/build target:

- The §2c table's **Realized-by** column IS the build target (e.g. `auth-coder`→`auth-gen`, `api-coder`→`api-first`, `data-access-coder`→`data-model`→`db-migration`, `config-coder`→`app-config`, `schema-coder`→`dto-schemas`, `domain-services-coder`→`domain-services`, `resilience-coder`→`resilience`, `iac-coder`→`iac-gen`/`stack-adapter`, …).
- **Design-stage (full route only) specialist architects** layer on top of the build agent: an Azure infra/sizing/region/SKU decision → `azure-architect` (ADR) → `iac-gen`; a full technical-architecture doc → `dat-architect`; context-window/prompt design → `context-engineering`; a live Azure incident/cost/WAF → `azure-sre`/`azure-cost`/`azure-waf`. A pure refactor/simplify (no behavior change) → `coder` directly, no architect/ADR.
- **Fallback** (Tier 3): a genuine feature with **no row matching** → plain `architect` (full) → `coder`; do **NOT** force-fit a specialist. A docs/config/refactor change routed `light` by §2 must **NOT** be dragged into the full architect pipeline — the §2 route wins.

Record the chosen specialist **and** `route_classification` in the spec ledger.

> **Skill vs agent (how to invoke):** the *generator* targets (`api-first`, `iac-gen`, `auth-gen`, `observability-gen`, `frontend-gen`, `data-model`, `db-migration`, `llm-gen`, `retriever`, `langgraph-workflow`, `security-review`, …) are **skills** — invoke via a `coder` subagent that READS `skills/<name>/SKILL.md` (§3), NOT `Task(subagent_type="<skill>")`. Only `architect`, `azure-architect/sre/deploy-verifier`, `dat-architect`, `coder`, `qa-tester`, `reviewer`, `red-team-destroyer`, `stack-adapter`, `context-engineering` are real **subagent types** (Task).

**Announce + delegate (transparency + lean context).** Before each delegation, print one line in the thread — `→ delegating to <agent> because <reason>` — so the routing is visible, not guessed. **Delegation is route-aware, not unconditional:**
- **`full` route:** run each stage as a subagent via the Task tool (architect, coder/generator, qa-tester, reviewer, red-team-destroyer). The main thread only orchestrates, parses verdicts, and reports, so each subagent's tool churn stays in its own ISOLATED context and the main window stays lean.
- **`light` route (default) / §2 trivial change:** do NOT force a subagent per stage — a 1-line/typo/docs fix shouldn't spawn coder+qa+red-team. Edit inline (or a single specialist subagent for real-logic changes); honor §2's right-sized validation.
- **No nested delegation:** a subagent does its assigned work **inline** — it cannot spawn further subagents (no Task tool inside a subagent). Only the top-level command thread delegates.

> <a name="terse-line"></a>**⚡ TERSE-MODE PREAMBLE (canonical — this command owns it; plan/auto reference this anchor).** Prepend to EVERY delegated subagent prompt: *"⚡ Respond in caveman/terse mode (token economy): drop articles, filler, pleasantries, hedging; fragments OK; keep ALL technical substance, exact `file:line`, code, and your VERDICT. Minimise output tokens."* The subagent's reply re-enters the (paid) main context, so terse output cuts cost on every delegation — keep its *thinking* full, only its *output* lean. **Verdict-bearing reviewers (`qa-tester`, `red-team-destroyer`, `reviewer`) stay terse but must NEVER drop a finding, caveat, or severity** — economy must not cost a real signal.

## 3. Run the pipeline with a CHECKPOINT per stage
Work on a dedicated branch: `git switch -c deliver/<slug>` (or reuse if resuming).
Before each stage, snapshot: commit WIP or `git stash push -m "deliver:<slug>:<stage>"`, and record the ref in the ledger.

- **architect / specialist** (full only): the §2b specialist (or generic `architect`) reads spec → writes `docs/adr/NNNN-*.md`, sets the decision the build stage implements against. **If `/fenrir:plan` already stubbed an ADR for this feature, REUSE/extend it — never author a second ADR for one feature.**
- **ADR red-team** — ledger stage `adr-redteam` (full + risk-path diffs only): `red-team-destroyer` attacks the **ADR** *before* code is written; its verdict line must name the stage (`VERDICT(adr): …`). `REDESIGN` = STOP, loop to architect; `FIX-FIRST` = fold into the spec before coding; `SHIP` proceeds. Distinct from the final `diff-redteam` below (different artifact, different ledger entry — resume can tell them apart).
- **coder / specialist generator** (full = always delegated; light real-logic = one specialist subagent or inline): implement against the spec + ADR via the §2b build agent. Generator skills ARE the specialized coders — per the §2b note, delegate to a `coder` subagent told to READ `skills/<name>/SKILL.md` (+ VERIFY) and apply it inline; generic `coder` is the fallback when none fits.
- **doc-keeper** (both): syncs `CHANGELOG.md` + affected README(s)/API-docs to the diff BEFORE review (so the changelog entry reviewer checks for already exists). Idempotent.
- **native correctness review** (full only): run `/code-review` **from this command body** (the main thread can use SlashCommand; a subagent cannot). Capture its findings as text.
- **reviewer** (full only): pass it the captured `/code-review` findings + the diff → it adds org PR-hygiene (conventional title, ADR link, changelog, profile) and returns a single advisory merge-ready verdict. It does NOT re-run `/code-review` itself.

### Validation gate — runs LAST before ship (right-sized per §2)
- **qa-tester** — ledger stage `qa` (full route + **light-with-REAL-LOGIC** — MANDATORY both; skipped ONLY on a §2 trivial change): writes new tests + any bug repro for the change and runs them. **Pass criterion:** the *new-coverage* tests are green AND any bug-repro **passes after the fix** — a repro that fails *before* the fix is qa's expected output, NOT a gate failure. Report real results.
- **diff red-team** — ledger stage `diff-redteam` (full = blocking on critical/high; **light + REAL LOGIC = blocking on ANY confirmed finding**; light + trivial = advisory-only, do NOT stop): `red-team-destroyer` adversarially reviews the **actual diff** — every bug, footgun, data-loss path, gate weakening; verdict line names the stage (`VERDICT(diff): …`). **On `full`,** a `REDESIGN`/`FIX-FIRST` driven by **critical/high** is a hard failure (STOP per §4); medium/low advisory. **On the real-logic light gate,** ANY confirmed finding (any severity) is a hard failure (STOP per §4) — this is the stricter contract for a real-logic change that had no architect/reviewer ahead of it. `SHIP` proceeds.
- **delivery-gates** (both): lint/type/test/coverage on the diff for fast local feedback. Advisory.

## 4. Failure handling — STOP, do not open a PR
- **Hard failure** (a stage errors, gates fail, reviewer = BLOCK, either red-team — `adr-redteam`/`diff-redteam` — returns `REDESIGN`/`FIX-FIRST` [on `full`: **critical/high**; on the **real-logic light gate**: **ANY confirmed finding**], or `qa`'s new-coverage tests are red / a repro still fails after the fix): STOP immediately, do NOT ship/PR, record the failing stage + checkpoint ref and report. `FIX-FIRST` = fold fixes in and re-validate, not ship-anyway.
- **Bounded re-validation (hard ceiling).** Re-validate at most **twice**; on a 3rd non-`SHIP`, STOP and hand the findings to a human (the red-team can always find *something* — only critical/high block, medium/low are advisory).
- **Resume**: re-invoking `/fenrir:deliver` reads the ledger, restores the last good checkpoint, and re-enters at the first non-passed stage — passed stages are not redone.

## 5. Hand off to ship (only if every stage passed)
Invoke `/fenrir:ship` to open the PR. Pass it the spec path and the ADR path so they're linked in the PR body.

## 6. Cost & US tracking (when the `dashboard/` board exists)
Track each spec as one costed **User Story**. *Mechanics + the time-sweep cost model live in `skills/us-cost-tracking/SKILL.md` (owned by the `delivery-tracker` agent) — follow them there; do not duplicate the doctrine here.* Actionable steps:
- **Before:** `move --kind story --id us-N --status in_progress` (one spec = one US).
- **After (or per stage):** `python -m backend.cli link --kind story --id us-N --session <session-id>` — idempotent per session+US, one entry per source (main vs each subagent), so coder/qa/reviewer subagent cost is captured. On success move the US to `review`/`done`.
- **Report:** `cli trace --us us-N`; subagent breakdown via the dashboard Subagents view.

Advisory bookkeeping, never a merge gate — couche-0 (CI + branch-protection) gates.

## Stop conditions
- No `org-profile.yaml` → route to `repo-bootstrap`, stop.
- Any hard failure → stop before PR, leave checkpoints intact for resume.
- This command never claims the merge is gated by it; CI + branch-protection do that.
