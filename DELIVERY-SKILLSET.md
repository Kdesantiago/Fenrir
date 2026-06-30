# Delivery Skillset — Org-portable delivery standard (v2)

> v2 = v1 corrected after red-team. 5 kill shots addressed. Read `## Kill shots → fixes` first.

## Core principle (fix #1, the most important one)

**A skill CANNOT enforce.** It is advisory text that the model *chooses* to follow. The real gate lives in deterministic INFRA: git hooks + CI required-checks + branch-protection-as-code. Skills = **fast local feedback**, not the barrier.

So the delivery standard = **3 distinct products**, not 1 skillset:

| Module | What | Primitive | Owner |
|---|---|---|---|
| **A. INFRA (couche 0)** | repo-template + hooks + CI + branch-protection. **The real gate.** | Deterministic files, not a model | Platform team |
| **B. GENERATORS** | profile-driven scaffolding (iac/auth/obs/front/llm) | Skills reading `org-profile.yaml` | Platform team |
| **C. ORCHESTRATION** | subagents + `/fenrir:deliver` + `/fenrir:ship` | Subagents + commands | DevEx |

All shipped as **1 versioned (semver) Claude Code plugin**, no per-repo `~/.claude` copy (= guaranteed drift).

---

## Skill & agent catalog

The full human-facing inventory: **55 skills** + **14 agents**, surfaced to Claude Code via frontmatter. One-line purpose per entry, taken from the real `description`. Grouped by concern; a skill is invoked by intent, or routed to as a build specialist by the **§2c router** in `/fenrir:deliver` (below). The eight newest layer-specific skills are tagged **(new)**.

### Delivery & gates

| Skill | Purpose |
|---|---|
| `repo-bootstrap` | Add couche-0 (hooks + CI + branch-protection + org-profile) to an EXISTING repo; idempotent |
| `delivery-gates` | Fast local lint+type+test+coverage on a diff — advisory, does not block |
| `security-review` | SAST + dependency/SBOM + threat-check on a git diff via native `/security-review` |
| `quality-master` | Ratchet UP to the strict tier — strict mypy, broad ruff, expert pytest strategy |
| `deps` | Supply-chain hardening — license allowlist, pinned+hashed lockfile, image signing, Renovate policy |
| `secrets` | Wire Key Vault / SOPS secret REFERENCES + rotation cadence; no literal at rest |
| `image-scan` | Container base-image / OS-layer CVE scan as a named CI required-check |
| `release` | Cut a SemVer release — bump, date the changelog, tag, publish |
| `doc-generator` | Aggregate & format EXISTING docs — README, API ref from code, changelog from commits |
| `memory-keeper` | Record/query in-repo git-tracked delivery memory (decisions, exceptions, drift, lessons) |
| `tech-debt` | Catalog debt markers + detect drift from recorded design, file onto the board |
| `us-cost-tracking` | Track work as board User Stories with REAL per-agent token/USD attribution |
| `workflow-efficiency` | Cost/speed a multi-agent workflow — per-stage model tier, prompt budget, cache-stable prefix |

### App-code specialists

| Skill | Purpose |
|---|---|
| `api-first` | Contract-first HTTP API — OpenAPI spec BEFORE code, then server stubs + client + contract tests |
| `frontend-gen` | Framework-aware frontend generation OR convention/a11y checks (react/vue/svelte/streamlit/html) |
| `app-config` **(new)** | Type the `core/` config layer — pydantic-settings, fail-fast required fields, `.env.example`, flag DECLARATION |
| `dto-schemas` **(new)** | pydantic v2 in/out DTOs in `schemas/` — typed fields, separate request/response, strict parsing |
| `domain-services` **(new)** | Implement a business use-case / domain rule in the `services/` layer |
| `cli` **(new)** | Build/extend a command-line interface — args, exit codes, stdin/pipe-friendly, `--help` |

### Data & persistence

| Skill | Purpose |
|---|---|
| `data-model` | Design/review a SQLAlchemy data model — normalized schema, access-pattern indexes, N+1 elimination |
| `db-migration` | Safe SQLAlchemy/Alembic migration — reviewed, reversible, lock-free, tested up→down→up |
| `file-storage` **(new)** | The `storage/` file layer — upload/download behind one blob port, streaming, boundary validation |

### Cross-cutting

| Skill | Purpose |
|---|---|
| `caching` | Add a cache layer — pattern, keys+TTL, invalidation, stampede protection, stale-data safeguards |
| `feature-flags` | Centralized runtime flag store (Azure App Config) — kill-switches, percentage flighting, targeting |
| `resilience` **(new)** | Make a cross-boundary call survive failure — timeout, transient-only retry+backoff, idempotency, fallback |
| `concurrency` **(new)** | Correct concurrent work — bounded parallelism, guarded shared state, cancellable+timed awaits/locks |
| `refactor` | Restructure WITHOUT behavior change — green baseline, smallest mechanical diff, same tests pass |
| `simplify` | Reduce code in place under a behavior-preserving guard — flatten, delete dead code, no new symbols |
| `optimize` | Optimize under ONE stated constraint (latency/throughput/memory/cost/bundle/cold-start), measure-first |
| `explain` | Explain existing code pedagogically at tunable depth/audience — read-only, grounded in `file:line` |

### Async & integration

| Skill | Purpose |
|---|---|
| `event-driven` | Message-driven producer/consumer over a queue/topic/stream with at-least-once reliability + DLQ |
| `cronjob` | Platform-correct scheduled job with the reliability defaults a naked cron lacks |
| `integration-client` **(new)** | Consume a THIRD-PARTY API/SDK — typed client, pagination, rate-limit, webhook verify in/out |

### Interface

| Skill | Purpose |
|---|---|
| `realtime-transport` | Server-push channel (WebSocket/SSE) with reconnect/backpressure/auth discipline |

### LLM / RAG

| Skill | Purpose |
|---|---|
| `llm-gen` | Typed LLM client for the declared provider + prompt mgmt + golden-set eval + cost/token tracking |
| `retriever` | RAG retriever — chunking, embeddings, vector-store adapter, hybrid search + rerank, recall@k eval |
| `knowledge-base` | Govern a RAG KB's content lifecycle — ingest + dedup, chunk/metadata taxonomy, freshness, citation |
| `langgraph-workflow` | Scaffold a LangGraph graph — typed State, pure-function nodes, routing, checkpointer, HITL interrupts |
| `online-llm-eval` | ONLINE (production-traffic) LLM eval — Langfuse LLM-as-judge scores, trace eval, RAGAS retrieval metrics |
| `llm-cost-monitor` | Monitor & budget LLM spend — per-route/model attribution, thresholds, dashboards, anomaly alerts |
| `ai-threat-model` | DESIGN-TIME LLM/agent threat model — map the OWASP-LLM attack surface to component + mitigation |

### Cloud / Azure (optional, advisory)

| Skill | Purpose |
|---|---|
| `iac-gen` | Profile-driven IaC — Helm chart / App Service IaC + env values + ArgoCD app + pipeline template |
| `gitops` | Pull-based GitOps loop for AKS/k8s — in-cluster operator (Flux/Argo CD) reconciling to a Git repo |
| `progressive-delivery` | Metric-gated canary / blue-green rollout (Argo Rollouts/Flagger) with auto-rollback |
| `load-test` | Synthetic load/perf scenarios (k6/Locust/Azure Load Testing) to exercise canary gates + SLOs |
| `observability-gen` | Vendor-neutral OTel init + semantic conventions + async resilience + SLI/SLO + alert rules |
| `alert-delivery` | Wire existing alert rules to a real notification channel (action group / Alertmanager receiver) |
| `error-budget` | SRE error-budget POLICY + its CI gate — freeze non-critical releases once the budget burns |
| `incident-runbook` | Incident-response PLAN + recovery playbook + generated Azure Automation/Functions/Logic-Apps automations |
| `azure-audit` | Read-only LIVE-subscription audit — inventory + azqr + resource health + policy + RBAC snapshot |
| `azure-cost` | Cut LIVE Azure spend — cost + Advisor + pricing into a dollar-quantified right-size/idle/reservation backlog |
| `azure-waf` | Score a LIVE subscription against the 5 Well-Architected pillars + a ranked remediation backlog |
| `azure-monitor-ops` | Run a specific KQL query against LIVE Azure telemetry (Monitor / App Insights / Log Analytics / ADX) |

### Reporting

| Skill | Purpose |
|---|---|
| `report` | SESSION report — files changed, decisions, tests run, board items touched, cost when a US is linked |

### Agents (14)

| Agent | Purpose |
|---|---|
| `architect` | Design a load-bearing decision BEFORE code, weigh trade-offs, DECIDE, and WRITE an ADR to disk |
| `dat-architect` | Write or audit a DAT — the full technical-architecture document for a system/service |
| `azure-architect` | Ground an Azure design in LIVE subscription reality + WAF, then write one Azure ADR |
| `context-engineering` | Design WHAT goes in the context window and HOW — prompt structure, retrieval ordering, token budget |
| `coder` | BUILD the minimal correct diff for a scoped change against the spec/ADR + active US |
| `qa-tester` | Author NEW unit/integration/edge tests for uncovered code; build a failing repro before a fix |
| `reviewer` | Merge-readiness review — org PR-hygiene (conventional title, ADR/changelog) on top of correctness |
| `red-team-destroyer` | Ruthless adversarial reviewer — every flaw, TOP 5 KILL SHOTS + WHAT TO ADD; attacks, never fixes |
| `doc-keeper` | Keep docs in sync with a change — CHANGELOG, READMEs, API docs; flag stale references |
| `delivery-tracker` | Trace a diff + telemetry onto the Agile board and attribute REAL token/USD cost to the right US |
| `stack-adapter` | Translate a standard delivery op into the company's exact wrapper commands when `stack-interface.yaml` exists |
| `azure-sre` | Triage an ACTIVE Azure incident against the real subscription, root-cause, propose ranked remediation |
| `azure-deploy-verifier` | Read-only deploy advisor — assert ready BEFORE, new-revision healthy AFTER; one GO/HOLD/ROLLBACK |
| `security-guardrail` | LLM guardrail for a UserPromptSubmit hook — judge a prompt for injection/destructive intent (opt-in) |

### §2c — deterministic specialist router (`/fenrir:deliver`)

After §2 fixes the **route** (`light`/`full`), §2c fixes the **build agent** — *which* specialist runs the build stage — orthogonal to the route (picking `api-coder` over generic `coder` never promotes a light change to full). Four ordered tiers, **first match wins**:

- **Tier 0 — explicit:** user `--agent=<name>` or a spec-ledger pin → use it, skip classification.
- **Tier 1 — deterministic dispatch (zero LLM tokens):** a 25-row glob + change-kind → specialist table, matched top-to-bottom; **risk-path rows (auth/security/migrations/iac) ordered first** so a risk change never falls through to a weaker specialist. The **Realized-by** column is the build target (a skill body read by a `coder` subagent, or a real agent). The dispatch covers the whole roster — e.g. `auth/`→`auth-gen`, `api/`→`api-first`, `schemas/`→`dto-schemas` (new), `services/`→`domain-services` (new), `core/settings`→`app-config` (new), `resilience/`→`resilience` (new), `async/`→`concurrency` (new), `clients/`→`integration-client` (new), `storage/`→`file-storage` (new), `cli/`→`cli` (new), …
- **Tier 2 — single cheap LLM classify:** ONLY when Tier 1 is genuinely ambiguous — one call, output constrained to a single specialist name. Records `route_classification: llm`.
- **Tier 3 — light default:** no row matched → generic `coder` (the deliberate home for open-ended backend logic). Never force-fit a specialist.

**Discipline:** exactly ONE specialist per atomic change — overlapping matches pick the single highest-priority row (risk rows dominate) and pass the other concern as a follow-up note; a genuinely cross-cutting change is the signal to escalate to `--full`, never to fan out. `route_classification: deterministic | llm` is recorded in the per-US ledger so the LLM path stays rare and auditable.

### `/fenrir:dashboard` command

One-command launch of the **bundled** dashboard (telemetry + Agile board) scoped to THIS repo — served on **http://127.0.0.1:8765** by default. Nothing is copied into your repo: a cross-OS stdlib launcher runs the plugin's own backend, passes your repo via `CLAUDE_PROJECT_DIR`, auto-picks a free port (8765 → +20 on conflict), and opens your browser.

---

## Couche 0 — INFRA (the real standard, definitely NOT skills)

This is where "standardize delivery" has teeth. Deterministic, outside the model's discretion.

| Component | Mechanism | Enforces what |
|---|---|---|
| `pre-commit` / `pre-push` hooks | git hooks (installed by `repo-bootstrap`) | lint, type, secret-scan, format — local, before push |
| CI required status checks | pipeline (Azure/GH Actions) | test, coverage, SAST, build — blocks merge |
| branch-protection-as-code | REST API via `set_branch_protection.py` (no gh/terraform); Terraform/Azure policy optional | PR required, required checks, CODEOWNERS review |
| versioned repo-template | template repo / cookiecutter | org structure, version assertion |

**Protocol**: `repo-bootstrap` generates these files + applies branch-protection via IaC. The skill installs; the INFRA enforces.

---

## org-profile.yaml (fix #2 — without it, generators spit out off-stack code)

Generators are NOT portable naked (OIDC≠SAML, k8s≠serverless, React≠Streamlit). They read a profile and **refuse on mismatch**.

```yaml
# org-profile.yaml — repo root
platform: aks          # aks | webapp | k8s | serverless | vm | ecs
framework: fastapi     # fastapi | express | spring | streamlit
auth_provider: entra   # entra | okta | keycloak | auth0
obs_backend: grafana   # grafana | datadog | cloudwatch | honeycomb | langfuse
llm_provider: anthropic # anthropic | openai | azure | bedrock | vertex
front: streamlit       # react | vue | svelte | streamlit | html | none
```

Generator with no matching profile → **hard stop, clear message**. No guessed scaffold.

---

## Couche 1 — SKILLS (`~/.claude/skills/<name>/SKILL.md` via plugin)

Trimmed vs v1: overlaps killed, secret-scan removed (→ hook), ADR removed from doc (→ architect).

| Skill | Job | Trigger (front-loaded description) | Fix note |
|---|---|---|---|
| `repo-bootstrap` | Init a NEW repo: structure, hooks, CI skeleton, branch-protection IaC, renovate, CODEOWNERS. **Idempotent, skip if exists.** | "initialize a NEW repo tooling — NOT for running checks" | Sole owner of the CI skeleton (collision fix §1) |
| `delivery-gates` | Runs lint+type+test+coverage **locally** = fast feedback. **Advisory.** Real gate = couche 0. | "run existing checks on a diff for fast local feedback" | Does not enforce; says so explicitly (fix #1) |
| `security-review` | Wraps native `/security-review`: SAST + SBOM + threat-check on a diff. **No secret-scan** (→ hook). | "SAST/SBOM/threat on a diff" | Secret-scan = single location (fix §1) |
| `doc-generator` | Aggregates/formats existing docs: README, API docs, changelog. **No ADR.** | "aggregate & format existing docs" | ADR belongs to `architect` (fix §1) |
| `iac-gen` | Profile-driven generator: Helm/ArgoCD if `platform=k8s`, otherwise refuse | "generate IaC for the declared platform" | Reads profile, refuses mismatch (fix #2) |
| `auth-gen` | Generator: OIDC/OAuth2 per `auth_provider`. **Never unreviewed auto-auth.** | "generate auth glue for declared provider" | Refuses without profile; auth = mandatory human review (fix #2, security) |
| `observability-gen` | OTel SDK init + semantic conventions; backend via env, never hardcoded | "generate vendor-neutral OTel init" | Backend = config (fix #2) |
| `frontend-gen` | Generator OR convention-checker per `front`; framework-aware a11y rules | "scaffold/check front for declared framework" | Refuses if framework unknown (fix #2) |
| `llm-gen` | Typed wrapper for `llm_provider`; golden-set eval, cost tracking | "generate LLM wrapper for declared provider" | 1 provider/profile; SDK to be verified against docs (fix #2) |

---

## Couche 2 — SUBAGENTS (`~/.claude/agents/<name>.md`)

Trimmed vs v1 (fix §7 — native overlap).

| Subagent | Verdict | Job |
|---|---|---|
| `architect` | **KEEP** — distinct, read+plan, restricted tools | Design, **ADR (decides+writes)**, trade-offs |
| `qa-tester` | **KEEP** — distinct tool-profile | Writes NEW tests + reproduces bugs (≠ gates, which run existing ones) |
| `reviewer` | **WRAP native** — no custom persona | Calls native `/code-review` + org-specific PR-hygiene rules only |
| `coder` | **KILL** unless a restricted toolset is needed | Otherwise = main thread's default behavior |

---

## Couche 3 — ORCHESTRATION (the "Project Manager", fix §4)

| Command | Job | Fixes applied |
|---|---|---|
| `/fenrir:deliver` | Pipeline: architect→coder→qa→reviewer→gates→PR | (a) **on-disk spec-artifact** = source of truth that each subagent re-reads (anti context-loss). (b) **deterministic routing by script** (LOC, risk files via globs), not LLM judgment. (c) **git checkpoint per stage** + resume. (d) real gates = CI, not the command. |
| `/fenrir:ship` | Opens PR + shows CI status | **Does NOT claim to enforce** — branch-protection (infra) blocks the merge, not `/fenrir:ship` (fix #1) |

**Adaptive resolved**: `light` is the **default** (inline edit or one specialist subagent); the **full** multi-agent pipeline is opt-in via `--full` or auto-triggered only for risky/large diffs (auth/iac/migrations/security path hits, or over the file/LOC threshold) — computed deterministically by script. Routing changes only design/review overhead; the qa-tester + red-team validation gate runs on **both** routes.

---

## Distribution (fix #4 — anti-drift)

- **1 Claude Code plugin, semver, 1 repo of record, changelog, owning team.**
- Repos consume a **pinned version**. Update = bump the pin. `~/.claude` copy forbidden.
- `delivery-gates` **asserts the repo-template version**, fails loud on mismatch.

---

## Added primitives (fix §6 — were missing)

Ordered by priority:

1. **Enforcement infra** (hooks + CI required-checks + branch-protection-as-code) — *already couche 0*
2. **Release mgmt**: semver, tags, auto changelog, release notes
3. **Supply-chain**: SLSA/provenance, artifact signing, pinned deps, license-policy enforce
4. **Secrets mgmt** (vault/SOPS) — ≠ secret *scanning*
5. **Env promotion + rollback + data-migrations** — delivery does not stop at the PR
6. **Dependency policy**: Renovate merge/pin rules, not just the file
7. **ADR-required CI check** on architectural diffs (≠ generating an ADR)

---

## Kill shots → fixes (summary)

| # | Kill shot v1 | Fix v2 |
|---|---|---|
| 1 | A skill cannot enforce the gate | Gate → couche 0 INFRA (hooks+CI+branch-protection). Skill = advisory |
| 2 | 5 non-portable scaffolds | `org-profile.yaml` + generators that refuse on mismatch |
| 3 | `/fenrir:deliver` multi-agent fragile | on-disk spec-artifact + deterministic routing script + checkpoints |
| 4 | Distribution = drift | 1 pinned semver plugin, owning team |
| 5 | 3 products in 1 | Split A(infra)/B(generators)/C(orchestration). **Ship A first** |

---

## Setup order (recommended)

1. **Couche 0 INFRA** + `repo-bootstrap` — without it, nothing enforces. This is the real mandate.
2. `org-profile.yaml` + 1 pilot generator (`iac-gen` on the current k8s stack)
3. `delivery-gates` + `security-review` (native wrap)
4. Subagents `architect` + `qa-tester`
5. `/fenrir:deliver` + `/fenrir:ship`
6. Release + supply-chain + secrets (added primitives)
