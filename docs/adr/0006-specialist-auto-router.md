# ADR 0006 — Specialist auto-router inside /fenrir:deliver

- Status: Proposed
- Date: 2026-06-29
- Deciders: architect agent
- Profile: platform=aks · framework=fastapi · auth=entra · obs=grafana · llm=anthropic · front=streamlit · vector_store=pgvector (the router is stack-agnostic; the profile only bounds which specialist can legally fire — a generator refuses off-stack)

## Context

The user's #1 ask: a scoped change should be **auto-delegated to the RIGHT specialist coder, in its OWN context**, to **reduce runtime tokens** and **stop main-thread pollution** (R2). Three artifacts already constrain the design:

1. **`commands/deliver.md` (post pass-1).** `light` is the default route (inline edit, or ONE specialist subagent for real-logic changes); the full `architect → coder → qa → reviewer → red-team` pipeline is **opt-in** (`--full`) or auto-triggered only on risky/large diffs (`commands/deliver.md:24-46`). §2b already carries a *prose* routing table (`commands/deliver.md:49-71`) keyed off "the work is about…". The router formalizes that table into a **deterministic, glob-first dispatch** so routing costs **zero LLM tokens** in the common case.
2. **ADR 0002 (Accepted) — no new coder agents.** feat-37 + us-96 decided the **generator skills ARE the specialist coders**, invoked by delegating to a `coder` subagent that READS `skills/<name>/SKILL.md` (NOT `Task(subagent_type="<skill>")`); generic `coder` is the fallback (`docs/adr/0002-*.md:48-55`, `commands/deliver.md:72`). This ADR MUST NOT mint `*-coder` agents — that would contradict an accepted decision. The roster spec's `api-coder`/`auth-coder`/… names are **logical specialist slots**, each realized by an existing skill or the generic coder.
3. **Roster spec (Pass 2)** (`docs/specs/specialist-coders-roster.md:59-67`) asks `deliver` to "gain a router: deterministic where possible (path/glob + change-kind), model-judged only when ambiguous," returning a **terse receipt** so little re-enters main context.

The gap this ADR closes: §2b is a *prose* table read and applied by the model on every delivery — that is an LLM classification step on the hot path. We replace it with a **deterministic glob+kind dispatch** evaluated by shell, falling back to a single cheap LLM call only on ambiguity, and to generic `coder` when nothing fits.

## Decision

Add a **deterministic specialist router** as a new step **§2c** in `commands/deliver.md`, between route selection (§2) and pipeline run (§3). It does NOT change the light/full decision (§2 owns that) — it only picks **which** build agent runs the build stage. Four ordered tiers, first match wins:

### Tier 0 — explicit override
If the user named a specialist (`--agent=<name>`) or the spec ledger pins one, use it. Skip classification.

### Tier 1 — DETERMINISTIC dispatch (glob + change-kind → specialist), zero LLM tokens
Compute the changed paths once (`git diff --name-only "$BASE"...HEAD`, or the spec's affected-paths for a not-yet-coded change), then match each against the dispatch table **top-to-bottom; first row that matches any changed path wins**. Risk-path rows are ordered first so a security/auth/migration change never falls through to a weaker specialist. Globs match at **any depth** (the monorepo nests `src/<svc>/…`) — anchor with `(^|/)`, never a bare `^`.

**Dispatch table — glob / change-kind → specialist (realized-by):**

| # | Path glob (any depth) | Change-kind signal | Specialist slot | Realized by (ADR 0002) |
|---|---|---|---|---|
| 1 | `**/auth/**`, `**/oidc/**`, `**/login/**` | authn/authz, token, session, guard | **auth-coder** | `auth-gen` skill |
| 2 | `**/security/**`, `**/crypto/**`; files matching `*sanitiz*`,`*secret*` | injection/XSS/CSRF/SSRF, secret handling | **security-coder** | `security-review` skill + `security-guardrail` |
| 3 | `migrations/**`, `**/alembic/**`, `**/versions/*.py` | schema migration / backfill | **migration-coder** | `db-migration` skill |
| 4 | `iac/**`, `**/helm/**`, `**/*.tf`, `**/*.bicep`, `**/charts/**` | infra / Helm / App Service | **iac-coder** | `iac-gen` (+ `stack-adapter` if `stack-interface.yaml`) |
| 5 | `**/*_test.py`, `tests/**`, `**/test_*.py`, `**/*.spec.*` | test-only diff | **testing-coder** | `qa-tester` agent |
| 6 | `src/*/api/**`, `**/routers/**`, `**/endpoints/**`, `**/openapi*.y*ml` | HTTP endpoint / contract | **api-coder** | `api-first` skill |
| 7 | `**/models/**`, `**/repositories/**`, `**/queries/**` (no `migrations/`) | ORM model / query / index | **data-access-coder** | `data-model` skill |
| 8 | `src/*/core/settings*`, `**/config/**`, `**/*settings*.py`, `.env*` | typed config / feature-flag | **config-coder** | `app-config` skill (+ `feature-flags`/`secrets`) |
| 9 | `**/observability/**`, `**/telemetry/**`, `**/logging/**` | OTel / SLO / alerts | **observability-coder** | `observability-gen` skill |
| 10 | front globs per profile (`**/*.tsx`,`**/*.vue`,`**/*.svelte`, streamlit `**/pages/**`) | UI component / page / a11y | **frontend-coder** | `frontend-gen` skill |
| 11 | `**/llm/**`, `**/prompts/**`, `**/agents/**` (app graph, not Fenrir `agents/`) | LLM client / RAG / graph | **llm-coder** | `llm-gen` / `retriever` / `langgraph-workflow` |
| 12 | `**/consumers/**`, `**/producers/**`, `**/messaging/**` | queue / topic / DLQ | **messaging-coder** | `event-driven` skill |
| 13 | `**/jobs/**`, `**/cron/**`, `**/schedulers/**` | scheduled / recurring job | **jobs-coder** | `cronjob` skill |
| 14 | `*.md`, `docs/**`, `CHANGELOG*`, `*.yaml`/`*.toml` config-only | docs / config / prose | **docs-coder** | `doc-keeper` agent (no architect; §2 light route wins) |
| — | anything else | general business logic | **(fallback)** | generic `coder` |

**Discipline — ONE specialist per atomic change.** The router returns **exactly one** specialist. If multiple rows match (a change spanning `api/` + `models/`), it does **NOT** fan out to two specialists (token blowout + split context). It picks the **single highest-priority row** (lowest #; risk rows 1-4 dominate) and passes the *other* concern as a note in the receipt for a follow-up US. A genuinely cross-cutting change that can't be served by one specialist is exactly the signal to escalate to `--full` (architect frames it), not to spawn a swarm.

### Tier 2 — single cheap LLM classification (ambiguity ONLY)
Invoke the model to classify **only** when Tier 1 is genuinely ambiguous: (a) **no row matched** but the change is non-trivial app logic, or (b) **two risk rows of equal priority matched** different files and the atomic-change rule can't disambiguate by priority. This is **one** classification call, output constrained to a single specialist name from the table (or `coder`). It is NOT a design step and NOT per-file. Record `route_classification: deterministic | llm` in the ledger so the LLM path is auditable and rare.

### Tier 3 — generic coder fallback
No row matched and Tier 2 returns no specialist → route to generic `coder` (ADR 0002's deliberate home for open-ended backend logic). Never force-fit a specialist (`commands/deliver.md:70`).

### Gate stays OPT-IN (preserve pass-1 light default)
The router is **orthogonal to** the full pipeline. Picking `api-coder` over generic `coder` does NOT promote a `light` change to `full`. The `architect → coder → qa → reviewer → red-team` gate fires **only** per §2 (`--full`, or auto-trigger on `RISK>=1 | FILES>5 | LOC>80`). On a `light` route the chosen specialist runs as the **one** subagent (or inline for a trivial change), honoring §2's right-sized validation. Risk-path rows (1-4) of the dispatch table coincide with §2's `RISK` globs, so a security/auth/migration change is *already* auto-`full` by §2 — the router just names the right hands inside that gate.

## Uniform specialist agent template (token-lean, consistent)

Every specialist slot — whether a future agent file or the prompt prepended to a `coder` subagent that reads a skill — uses this **capped skeleton**. Precision over prose; hard cap **~40 body lines**. Frontmatter `description` carries the **Use-when / NOT-for-X→use-Y / Refuses-when** triad so routing and self-policing are legible.

```
---
name: <slot>-coder
description: >
  Use-when: <the one concern, path-anchored>.
  NOT-for: <X> → use <other-specialist>; <Y> → use <other>.
  Refuses-when: org-profile mismatch (<key>) | asked to design (→ architect) |
                asked to gate/merge (→ reviewer) | touches a gate file (.claude/, CI).
tools: Read, Grep, Glob, Edit, Write, Bash      # core app-code scope; NO cloud MCP unless Azure layer opted-in
model: inherit
---

# <Slot> coder
One-line identity: the implementer for <concern>, own context, terse receipt.

## Cahier des charges — "done right" checklist   (≤8 bullets, the domain's load-bearing invariants)
- [ ] <invariant 1 — e.g. auth: validate token sig+aud+exp at the boundary, never trust client>
- [ ] <invariant 2 …> ; <invariant 3 …>
(These are the non-negotiables qa-tester + red-team will check; keep ONLY what is domain-specific.)

## Core behavior (zero cloud)
Read ground-truth (spec/ADR + active US) → read siblings for convention → minimal correct diff →
prove the narrow path runs (Bash). Match org-profile (framework/front); refuse off-stack.

## Optional Azure layer (pointer, not inlined)
If org-profile platform=azure / cloud_layer:azure → consult <skills/<azure-skill>>. The Azure layer
NEVER loads or blocks for a local user; core ships without any az/terraform/kubectl.

## Receipt (TERSE — what re-enters main context)
1. Diff summary: files touched (path → what), the US/spec implemented.
2. Verified: exact command run + actual result (1 line).
3. Deferred / spec-mismatch / cross-cutting note for a follow-up US. ≤6 lines total.
```

The receipt contract is the token lever: the subagent's *thinking* stays full, only its *output* is lean (mirrors `commands/deliver.md:79` terse-mode preamble). MAP slots reuse the existing skill body as the cahier des charges instead of re-authoring it.

## Token-reduction mechanics (explicit levers)

a. **Deterministic routing = no LLM call to route.** Tier 1 is shell glob-matching; the model is invoked for routing **only** on real ambiguity (Tier 2) — replacing today's per-delivery model read-and-apply of the §2b prose table. Routing tokens drop to ~0 on the common path.
b. **One specialist, own ISOLATED context.** The specialist's tool churn (Reads, Greps, failed Bash) stays in its window, never the main thread (R2). One specialist per atomic change — no fan-out — so context cost is bounded to a single subagent, not N.
c. **Terse receipt re-enters main context.** Diff-summary + one verified line + deferred note (≤6 lines) is all the main thread pays for, instead of the full build transcript.
d. **Skill-surface consolidation lowers selection cost (advisory; not executed here).** A smaller, collision-free trigger space means the *model* (and the Tier-2 fallback) spend fewer tokens disambiguating which skill/specialist applies. Proposed merges/renames/retires below.

### Consolidation backlog (advisory — do NOT execute in this ADR)

| Cluster | Problem | Proposed action |
|---|---|---|
| **Name-collisions with native commands** | `simplify` skill vs native `/simplify`; `security-review` skill vs native `/security-review` — every description must spend a clause saying "NOT native /…", and the model can pick the wrong one. | **Rename** the wrappers to disambiguate (`simplify` → `kiss-reduce`; `security-review` → `diff-security-scan`), or **retire** the thin wrapper and call the native command directly from the command body. Shrinks two trigger-space collisions. |
| **Cost trio** (`llm-cost-monitor`, `us-cost-tracking`, `azure-cost`) | Three "cost" skills, each burning a description clause cross-NOT-ing the other two (`skills/*/SKILL.md:3`). High mutual ambiguity at selection time. | **Keep all three** (genuinely different subjects: LLM spend / delivery token-cost / Azure bill) but **rename for an instant-discriminating prefix**: `llm-spend-monitor`, `delivery-cost-tracking`, `azure-bill-cost`. Cuts the cross-NOT clauses; no merge (they don't overlap in function, only in the word "cost"). |
| **Azure live-subscription trio** (`azure-audit`, `azure-cost`, `azure-waf`) | All three: "LIVE Azure subscription via az MCP, read-only, advisory," overlapping evidence (`advisor`+`resourcehealth`+inventory). `azure-waf` already *consumes* `azure-audit`'s inventory. | **Merge** into one `azure-review` skill with a `--mode {audit,waf,cost}` flag (shared inventory pass, mode-specific scoring), OR keep `azure-audit` as the inventory primitive and fold `azure-waf` into it as a scoring mode. Collapses 3 trigger entries → 1. |

Net effect: ~5 collisions/overlaps removed from the trigger surface → cheaper, more reliable specialist selection. Sequencing and exact renames are a follow-up US, gated by qa + red-team like any change.

## Alternatives considered

- **Mint real `*-coder` agent files per roster slot.** Rejected — directly contradicts **ADR 0002 (Accepted)**: "add NO new specialized coder subagent" (`docs/adr/0002-*.md:48`). Each agent is standing maintenance for ~zero marginal correctness over "generic coder + skill." The slots are logical; they resolve to existing skills.
- **LLM-classify every change (drop deterministic tier).** Rejected — that is exactly the per-delivery routing-token cost this ADR removes. Globs decide the overwhelming majority deterministically; the model is the rare fallback.
- **Fan out to every matching specialist in parallel.** Rejected — N subagents for one atomic change is the token blowout the user wants gone, and split context produces inconsistent diffs. One specialist per atomic change; cross-cutting → escalate to `--full`.
- **Execute the consolidation here.** Rejected — the prompt scopes consolidation to *advisory*. Renames/merges touch skill frontmatter + every cross-ref and need their own qa+red-team gate; bundling them would bloat this change and break the atomic-US rule.

## Consequences

Positive:
- Routing is deterministic, auditable (`route_classification` in the ledger), and ~free on the hot path; the §2b prose table becomes an executable dispatch table.
- Main-thread pollution drops: one specialist, isolated context, ≤6-line receipt — the R2 ask, mechanized.
- The uniform template keeps every specialist token-lean and consistent; MAP slots reuse skill bodies, no duplication.

Negative / risk:
- **Glob drift.** A repo whose layout diverges from the table's globs falls to Tier 2/3 more often — mitigated by the explicit `--agent` override (Tier 0) and the generic-coder fallback (never a hard fail). The table is a strong default, not a contract.
- **Atomic-change rule can under-serve a legitimately cross-cutting change** — by design it escalates to `--full` rather than fanning out; the architect then frames the split into per-concern US.
- Consolidation is **deferred**, not done; until then the trigger space keeps its current collisions and the Tier-2 fallback is marginally more likely.

## Implementation notes for downstream

- **coder:** add **§2c** to `commands/deliver.md` (after §2, before §2b/§3) with the dispatch table above; rewrite §2b to *reference* §2c's deterministic tiers instead of carrying a separate prose table. Do **NOT** create any `agents/*-coder.md` (ADR 0002). Encode the one-specialist-per-atomic-change rule and the `route_classification` ledger field.
- **qa-tester:** cover (1) each risk-path glob routes to its risk specialist and is also auto-`full` by §2; (2) a multi-match change yields exactly ONE specialist (highest-priority row), not a fan-out; (3) no-match non-trivial → Tier-2 single call → else generic `coder`; (4) a docs/config change stays `light` and is NOT dragged into the architect pipeline.
- **reviewer:** confirm the PR adds NO new agent files, leaves the §2 light/full logic byte-identical, and that the dispatch globs use `(^|/)` (any-depth) not bare `^`. The consolidation backlog is advisory — any actual rename/merge must arrive as its own US.
