# 0002 — Specialized coder roster: no new coder subagent (us-96)

- Status: Accepted
- Date: 2026-06-28
- Deciders: architect agent
- Profile: platform=aks · framework=fastapi · auth=entra · obs=grafana · llm=anthropic · front=streamlit · vector_store=pgvector (decision is roster/process, not stack-specific; profile only bounds which generators can fire)

## Context

User wants "specialized coders." feat-37 already decided **the generator skills ARE the specialized coders**, routed as subagents — codified in `commands/deliver.md:49-71` (§2b routing table) and `commands/deliver.md:85` (§3: *"The generator skills ARE the specialized coders … route to that generator run as a subagent; the generic `coder` subagent is the fallback when no generator fits"*).

us-96 asks the narrower question: **does any delivery domain have a real GAP — no generator covers it — that warrants a NEW thin coder subagent?** Rule from the user: add one ONLY where a genuine gap exists; otherwise conclude none needed and avoid roster explosion. Each subagent is a maintained system-prompt (a standing cost), so the bar is a real domain the existing routing cannot serve, not a nice-to-have.

### Coverage map — delivery domain → build agent (grounded in skill frontmatter)

| Delivery domain | Covered by | Evidence |
|---|---|---|
| HTTP API contract / endpoint | `api-first` | `skills/api-first/SKILL.md:3` |
| DB schema / query / index design | `data-model` | `skills/data-model/SKILL.md:3` |
| Schema migration (Alembic) | `db-migration` | `skills/db-migration/SKILL.md:3` |
| IaC / Helm / App Service / pipeline | `iac-gen` (+ `stack-adapter` for wrappers) | `skills/iac-gen/SKILL.md:3` |
| Auth / OIDC / OAuth2 wiring | `auth-gen` | `skills/auth-gen/SKILL.md:3` |
| Observability / OTel / SLO / alerts | `observability-gen` | `skills/observability-gen/SKILL.md:3` |
| Frontend component / page / a11y | `frontend-gen` | `skills/frontend-gen/SKILL.md:3` |
| LLM client / prompts / offline eval | `llm-gen` | `skills/llm-gen/SKILL.md:3` |
| RAG retrieval (chunk/embed/hybrid) | `retriever` | `skills/retriever/SKILL.md:3` |
| RAG content lifecycle / governance | `knowledge-base` | `skills/knowledge-base/SKILL.md:3` |
| LLM workflow / agent graph | `langgraph-workflow` | `skills/langgraph-workflow/SKILL.md:3` |
| Cache layer (aside/read-through/TTL) | `caching` | `skills/caching/SKILL.md:3` |
| Message-driven producer/consumer | `event-driven` | `skills/event-driven/SKILL.md:3` |
| Server-push / WebSocket / SSE | `realtime-transport` | `skills/realtime-transport/SKILL.md:3` |
| Scheduled / recurring job | `cronjob` | `skills/cronjob/SKILL.md:3` |
| Behavior-preserving restructure | `refactor` | `skills/refactor/SKILL.md:3` |
| In-place KISS reduction | `simplify` | `skills/simplify/SKILL.md:3` |
| Perf under one constraint | `optimize` | `skills/optimize/SKILL.md:3` |
| Company Azure wrapper command mapping | `stack-adapter` (agent) | `agents/stack-adapter.md:3` |
| **General backend / business-logic service** | **generic `coder`** | `agents/coder.md` — no dedicated skill; explicit fallback at `commands/deliver.md:69` |
| **Test-suite authoring** | `qa-tester` (agent) | already exists; not a coder concern |

### Candidate gaps weighed (handled only by generic `coder` today)

- **General backend / business-logic service** — the residual feature work after the contract/schema/auth/obs slices are carved off by the generators above. This is the deliberate home of the generic `coder` (`commands/deliver.md:69` "Generic app feature / fix, no specialist fits → architect → coder"). It is *boundless* (any domain logic), so no single system-prompt makes it more "correct" than the generic coder reading siblings + spec (`agents/coder.md:19-21`). A "backend-coder" would duplicate the generic coder with no added domain constraint.
- **CLI tooling / scripting / automation** — small surface, no stack-specific reliability discipline a skill would encode; generic `coder` + `repo-bootstrap` conventions suffice. No recurring failure mode unique to it.
- **Data pipelines / ETL** — partially decomposes into existing skills: scheduling → `cronjob`, message flow → `event-driven`, schema → `data-model`/`db-migration`. The residual transform logic is business logic → generic `coder`. A dedicated "etl-gen" would mostly re-route to skills it doesn't own; premature without a concrete repo need.
- **Test-only authoring** — already owned by `qa-tester` (`agents/qa-tester.md`); a "test-coder" would be a duplicate roster entry.
- **Mobile / desktop** — out of profile entirely (`front` ∈ react|vue|svelte|streamlit|html; `platform` ∈ aks|webapp|k8s|serverless|vm|ecs — `templates/org-profile.yaml:4,9`). Designing a coder for a stack Fenrir does not target is gold-plating a non-problem.

## Decision

**Add NO new specialized coder subagent.** The generator/skill roster + the generic `coder` fallback already cover every delivery domain Fenrir targets. The "specialized coders" the user wants already exist — they are the generator skills routed as subagents per `commands/deliver.md:49-85`. The single uncovered region (open-ended backend/business-logic) is *correctly* served by the generic `coder`, which derives correctness from the spec/ADR + sibling conventions (`agents/coder.md:15-21`), not from a domain system-prompt that cannot be written for "all business logic."

Routing-to-generators beats minting new agents because:
- **A skill ≠ an agent.** A generator skill is invokable inside the existing `coder`/specialist subagent. New domains are absorbed by **adding a skill and one §2b table row**, not a new maintained agent system-prompt — cheaper, and it keeps domain discipline (the VERIFY.md gate) attached to the work.
- **Each agent is standing maintenance.** 14 agents already exist (`agents/*.md`). A new coder agent must be kept terse, in-lane, profile-aware, and consistent with `coder.md` forever; the marginal correctness over "generic coder + relevant skill" is ~zero for the candidate gaps.
- **No gap is load-bearing.** Every candidate above either (a) already has a skill, (b) decomposes into existing skills, or (c) is the generic coder's deliberate domain, or (d) is off-profile.

## Alternatives considered

- **Mint `backend-coder` for business-logic services.** Rejected: it would duplicate `agents/coder.md` with no narrower domain contract — "all backend logic" is not a domain a system-prompt specializes; the generic coder + sibling-reading already is that role.
- **Mint `data-pipeline-coder` (ETL).** Rejected: decomposes into `cronjob` + `event-driven` + `data-model`/`db-migration`; the residue is business logic. Adds a router that mostly delegates to skills it doesn't own. Revisit only if a real repo shows a recurring ETL failure mode none of those skills catch (deferred).
- **Mint `cli-coder` / `script-coder`.** Rejected: no stack-specific reliability discipline to encode (unlike `cronjob`'s no-double-run or `caching`'s stampede defense); generic coder suffices.
- **Mint `mobile-coder` / `desktop-coder`.** Rejected: off-profile (`templates/org-profile.yaml:4,9`). Designing for an untargeted stack is gold-plating.
- **Convert existing skills into standalone coder agents.** Rejected: a skill already runs *inside* a subagent (§3); promoting each to its own agent multiplies maintenance and breaks the "skill carries its own VERIFY gate" model for no routing benefit.

## Consequences

Positive:
- Roster stays at its current size — no new system-prompt to maintain; avoids the explosion the user warned against.
- The "specialized coder" need is met by existing routing — feat-37's model is reaffirmed, not re-litigated.
- New domains have a clear, cheap extension path: **add a skill + a §2b row**, not an agent.

Negative / risk:
- Open-ended backend logic leans on the generic `coder`'s convention-matching (`agents/coder.md:19-21`); quality depends on good siblings + a sharp spec, with no domain prompt as a safety net. Mitigation: that work still passes the full `qa-tester` + `red-team-destroyer` gate (`commands/deliver.md:90-93`) and the human merge gate (CI required-checks + branch-protection) — unchanged.
- ETL as a first-class domain is **deferred**, not denied; if real repos surface a distinct ETL failure mode, reopen with a `data-pipeline` *skill* (preferred) before an agent.

Follow-ups:
- None required. No code, no agent files, no command edits — feat-37's §2b/§3 already encode the chosen model. This ADR is the decision record for us-96.
- Human merge gate is unchanged and remains mandatory; nothing here is auto-anything.

## Implementation notes for downstream

- **coder:** nothing to build. Do NOT create any new `agents/*-coder.md`. If a future US adds a domain generator, add the skill under `skills/<name>/` (with `SKILL.md` + `VERIFY.md`) and a single row in `commands/deliver.md` §2b — do not add an agent.
- **qa-tester:** no new test surface from this ADR (it is a decision record, zero code).
- **reviewer:** verify the PR for us-96 contains ONLY this ADR (`docs/adr/0002-*.md`) — no edits to `agents/` or `commands/`. Any agent-file change would contradict the decision and is a defect. Confirm the §2b table in `commands/deliver.md:49-71` is left intact.
