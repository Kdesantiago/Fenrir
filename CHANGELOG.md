# Changelog

All notable changes to `fenrir`. Format: [Keep a Changelog](https://keepachangelog.com/), [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Agile-granularity hygiene gate** — `BoardStore.audit()` + `cli audit` + `GET /api/board/audit` flag US that aren't ATOMIC: a US whose real cost exceeds a threshold (default $50) or that holds >40% of its epic's cost is an *umbrella* → "decompose into the real atomic US". Also flags orphan US and empty features. Encodes the rule "a $400 US is a problem" (it flagged the session-umbrella us-49 at 100% of its epic). The `delivery-tracker` agent now enforces the doctrine when it authors the board: **US = atomic (one thing, one acceptance criterion; sub-steps are Tasks), Feature = a business/dev capability grouping its US, Epic = a program; never a per-session umbrella US; `set-us` per atomic US before the work, one US per chunk** (a single fan-out doing N US' worth of work can't be split afterward).
- **Per-US cost attribution (mandatory, automatic, with rollup)** — every spend is now traced to a *specific* US, not a per-session lump. Replaces the whole-session `link` with a `reconcile` pass: subagent runs are attributed to the US that was active **when each ran** (time-sweep over a `set-us` ledger — robust even if SubagentStop never fired), and main-thread cost to the current US as a watermark delta. main and subagent are disjoint telemetry sources → no double-count; each run attributed once (idempotent). One in-process CLI pass (`cli reconcile`, ~2s for 198 runs) called by the `tracking-finalize` hook on Stop + SessionEnd, so cost updates live. New CLI: `session-cost`, `session-runs`, `reconcile`; `cli log` gains cache + `--source`; engine gains `set-us` + a per-US `finalize`. **Rollup proven exact on real data: Epic = Σ Features = Σ User Stories** (`costs()` already aggregated; now the leaves carry real cost). Proven: 198 runs split $177/$230 across two US by time, rollup $407 consistent at every level.
- **Multi-agent cost/speed/quality efficiency** ([ADR 0001](docs/adr/0001-multi-agent-cost-efficiency.md)) — reframes the cost: cache-read is 0.1× input, so caching already saves ~10× (measured: actual ~$677 vs ~$3.5k uncached = **$2.9k saved**, 98% hit-ratio). The bill is **context volume × model tier**, not the cache.
  - **Dashboard cache-efficiency view** — `telemetry.efficiency()` + `GET /api/telemetry/efficiency` + an "Cache efficiency" panel: per model the cache hit-ratio, actual vs **uncached-equivalent** cost, and savings. A high-spend / low-hit-ratio model is the real waste to target. **Savings can go NEGATIVE** when cache writes (1.25× premium) exceed reads — surfaced as the waste signal.
  - **`workflow-efficiency` skill** (45 skills) — the authoring rubric for multi-agent workflows: tier the model per stage (mechanical → Haiku/Sonnet, judgment → Opus — the #1 overspend), budget prompts (pass file refs not inlined blobs), keep prefixes cache-stable, cap fan-out, tier effort. Advisory; the cache-efficiency view measures the result. Carves vs `context-engineering` (product context) and `llm-cost-monitor` (runtime spend).

### Fixed
- **Dashboard cost ~3× too high for Opus** — the price book keyed all `opus` models at the legacy Opus 4.1 rate ($15/$75). Now version-aware: Opus 4.5–4.8 = $5/$25, Opus 4.1 = $15/$75, Fable/Mythos 5 = $10/$50, Sonnet = $3/$15, Haiku 4.5 = $1/$5, Haiku 3.5 = $0.80/$4 (cache rates still derived 1.25×/2×/0.1× input, matching the published table). Version keys match before the generic family key. Historical `work_log` entries keep the cost computed at log time — re-`link --refresh` a session to recost it.

### Added
- **Dashboard cache-token visibility (everywhere)** — every cost surface now shows cache, so the cost is self-explanatory:
  - Telemetry tables (By-model / By-skill / Source / Subagent-type / Subagent-runs) gain **Cache W** + **Cache R** columns; KPIs add **Cache cost** (% of spend, read vs write) + **Fresh cost**.
  - The **per-US** path carries cache too: `WorkLogEntry` gains `cache_write_tokens`/`cache_read_tokens`; `cli link` (per-source) and `cli attribute` (per-run, via `_run_tokens`) populate them; `BoardStore.costs()` rolls them up per US/Feature/Epic/agent; the **Cost trace** + the per-US cost modal show Cache W/R.
  - `telemetry._group` + `summary()` add the cache token sums + a `cost_breakdown` (input/output/cache_read exact, cache_write = remainder so it reconciles to total).
  - This explains the apparent cost "incoherence": for heavy multi-agent runs **cache reads dominate** (≈80% of spend — agents re-reading large cached contexts), which the input/output-only columns hid. The per-token price was already correct.
- **Red-team hardening of the v1.4 wave** — a `red-team-destroyer` pass over all 17 new skills/agents, fixes applied: made VERIFY Blocking checks genuinely **falsifiable** (scoped to the resolved module, behavioral not keyword-presence; e.g. caching TTL/secret checks, knowledge-base taxonomy/dedup), fixed a `data-model` VERIFY globstar bug (bash globstar off by default → `find`), resolved cross-skill responsibility collisions (`data-model`↔`api-first` on pagination; `event-driven`↔`caching` on the dedup store), corrected `event-driven` to choose the messaging primitive from the **delivery contract** (ordering/throughput) and read `framework` (multi-language output) instead of keying off `platform`, and removed a false `knowledge-base`→gitleaks claim (gitleaks scans commits, not ingested corpora).
- **Dashboard flow metrics** (us-39/40) — the board now records a timestamped **status-transition log** (`set_status` appends a `Transition`; `models.Transition` added to every item), and `BoardStore.flow_metrics()` derives Kanban/DORA-style flow: **cycle time** (in-progress→done, avg/p50/p85), **weekly throughput**, current **WIP + aging**, and a reproducible **Monte-Carlo forecast** ("when is the backlog done", p50/p85 weeks). Exposed via `cli metrics` and `GET /api/board/flow`. 5 deterministic tests (seeded forecast, explicit timestamps).
- **Capability extension — 14 skills + 3 agents** (44 skills, 13 subagents), designed + dedup-checked by a red-team pass (9 redundant candidates killed/merged: e.g. `graphql`/`grpc` already scoped out by `api-first`, `azure-landing-zone` = `iac-gen`, `azure-finops` merged into `azure-cost`, `azure-deploy` into a verify agent).
  - **Author & evolve code**: `refactor` (behavior-preserving restructure under a green-test guard), `simplify` (DRY/KISS reduction, test-guarded — distinct from the native `/simplify`), `optimize` (under ONE declared constraint, measure-first), `explain` (didactic mental-model walkthrough), `report` (session digest: files/decisions/tests/cost/board).
  - **Tech-specific**: `data-model` (ORM/index/query design — not migrations), `caching` (pattern/TTL/invalidation), `event-driven` (producer/consumer delivery discipline over a bus), `knowledge-base` (RAG content lifecycle atop `retriever`), `realtime-transport` (WebSocket/SSE server-push: handshake auth, heartbeat/reconnect/resume, backpressure, scale-out backplane).
  - **Azure live-ops** (operate a LIVE subscription via the `az` MCP, **read-only/advisory** — distinct from the file-emitting generators): `azure-audit` (azqr + resource-health + policy posture), `azure-cost` (FinOps on live spend), `azure-waf` (5-pillar Well-Architected scoring), `azure-monitor-ops` (KQL triage over Monitor/App Insights/Log Analytics).
  - **Azure agents**: `azure-architect` (live-grounded Azure ADR, WAF-aligned), `azure-sre` (live incident responder via `az` sreagent/applens/monitor), `azure-deploy-verifier` (read-only pre-flight + post-deploy GO/HOLD/ROLLBACK recommendation; never mutates — CI/progressive-delivery execute).
  - Each ships `SKILL.md` + `VERIFY.md` (agents: frontmatter + machine-parseable output contract); built by a fan-out workflow with an adversarial verify pass that self-healed phantom-sibling references, wrong carve targets, and over-length descriptions.
- **Automatic + enforced delivery tracking** — closes the loop so work is traced to the Agile board without manual CLI, and untracked work can't merge. *Skills advise, infra enforces*: the deterministic floor is hooks + a CI gate; the smart part is a subagent.
  - **Auto-US + live cost**: `tracking-open` (UserPromptSubmit) ensures the session's US exists from the first prompt (no commit needed); `tracking-finalize` runs on **Stop and SessionEnd** and `link --refresh`es the session's REAL cost onto the US every turn (board gains `clear_session_links` + `link --refresh` so cost updates instead of being one-shot). `set-us` steers the active US so subagent runs attribute per-US live (`collect-run` attributes on SubagentStop). Engine resolves the **per-project** board path via the dashboard's own `config` (fixes duplicate-US creation against the legacy single-file path).
  - **`delivery-tracker` subagent** (10 subagents) — turns a git diff + session telemetry into the right `Epic → Feature → User Story → Task` tree and attributes the session's REAL token/USD cost to the correct US via the dashboard board CLI (idempotent; re-parents the hooks' catch-all US, picks `link` vs per-run `attribute`). Authors tracking, never edits code; refuses when no `dashboard/` is present.
  - **`scripts/track_session.py` engine** — the deterministic half the hooks call without a model: `ensure-us` / `collect-run` / `finalize` / `check`. Reads the board read-only for lookups, mutates ONLY via the CLI (one source of truth). **Fail-open** everywhere (no dashboard / broken CLI → no-op, never blocks delivery).
  - **Four hooks** (13 hooks total): `tracking-open` (UserPromptSubmit — auto-ensures the session's US), `tracking-collect` (SubagentStop — ledgers + live-attributes each subagent run), `tracking-finalize` (Stop + SessionEnd — refresh-links the session's real cost), `tracking-guard` (PreToolUse Bash — makes tracing a `git commit` obligatory). Guard modes via `FENRIR_TRACK_ENFORCE`: default `auto` (auto-creates a US, never bricks a session) vs `strict` (DENY an untraced commit). `FENRIR_TRACK_DISABLE=1` turns tracking off. Runs alongside `delivery-guard` (most-restrictive decision wins).
  - **CI `delivery-trace` required check** (`templates/ci/delivery-trace.yml`) — the authoritative gate: a PR can't merge unless a commit/PR-body references a `us-<N>` that exists on the board (passes when no dashboard board is present). Add to `branch-protection.tf` `required_checks` to enforce.
  - `repo-bootstrap` now also copies `scripts/track_session.py` → `.claude/scripts/` and wires the three hooks (SubagentStop / SessionEnd / PreToolUse). 17 new hook tests (safety fail-open units + dashboard-integration), `.claude/tracking/` git-ignored.

## [1.3.0] — 2026-06-28

### Added
- **Monitoring dashboard** (`dashboard/`, companion web app — not a plugin component): a local FastAPI + SPA that gives a tech lead a real monitoring surface.
  - **Telemetry** — parses real `~/.claude` transcripts into tokens/cost aggregated by model, skill (`attributionSkill`), day, and source (main thread vs subagent), with USD **derived** from a configurable price book (`backend/pricing.py`). Read-only.
  - **Agile board** — an `Epic → Feature → User Story → Task` kanban (drag-drop status, charts, filters), stored as git-trackable JSON (`data/board.json`), that **agents drive themselves** via `python -m backend.cli` (epic/feature/story/task add, move, assign, log) — same store as the REST API. Stories/tasks cross-link to real telemetry via their `work_log`.
  - Stack: FastAPI + vanilla-JS SPA (Chart.js + SortableJS via CDN, no build step). 61 backend tests (board/telemetry/pricing) + a `dashboard` CI job (ruff/mypy/pytest); the SPA was verified end-to-end against the running app.
  - **Project-scoped telemetry** — defaults to the current repo's Claude Code project (auto-detected), with a header project selector + `?project=` (`all` = every project); `/api/projects` + a shared `config.py` so the CLI and API resolve board/`~/.claude` identically.
- **Per-US cost accounting** (dashboard) — answer "what did a User Story cost?": `GET /api/board/costs` (per Epic/Feature/US tokens + USD, broken down per agent), a chronological **cost trace** (`GET /api/trace`, `cli trace`), and **subagent attribution** `GET /api/telemetry/subagents` — which named subagent ran, when, on what model, how long, how much, identity from `agent-*.meta.json` and tokens from each subagent's own transcript. **Reconciled, no double-count** (`attributed + unattributed == subagent total`, asserted by a test — a v1 design double-counted and was caught by a red-team). `cli link` now writes one entry per source (main vs subagent) and is idempotent per `(session, US)`; `WorkLogEntry` gains `source`/`subagent_type`; pricing strips the `[1m]`-style tier suffix. New advisory skill **`us-cost-tracking`** (30 skills) drives the formalism; 14 more backend tests (75 total). The Stop/SessionEnd auto-attribution hook and "force" framing from the first design were **dropped** (red-team: dead in consumer repos, can't block) in favor of an explicit `cli link`.
- **`coder` subagent** (9 subagents) — the missing implementer in the `architect → coder → qa-tester → reviewer` flow (previously the main thread, which has no `toolUseResult`). As a real Task subagent its token spend is now attributable to the US. `/fenrir:deliver` delegates the build to it and documents the US/cost formalism (§6).

### Changed
- **Kanban is now per-project** — the board store is `data/boards/<project-slug>.json`; the dashboard auto-detects the current repo's board and the header project selector re-scopes the kanban (board fetch + every mutation + costs + trace carry `?project=`). The single `data/board.json` was migrated to its project file.
- **Higher-fidelity cost estimate** — the price book now stores a base `(input, output)` rate per family and **derives** cache rates from it (so a contract change is one number), and prices cache **writes by TTL** — 5-min (1.25× input) vs 1-hour (2× input) — from `usage.cache_creation`, instead of one flat cache-write rate. Extended-thinking tokens are documented as already counted (billed as output). Named, un-modeled gaps: web-search requests, batch/priority tiers, `[1m]` long-context premium. (`rates_for` now returns a rate dict.)
- **Per-US cost is now meaningful, not a lump** — new `cli attribute --run <run_id>` charges ONE subagent run's real tokens/cost to a US (distinct per run), keyed on a stable `agent-<id>` (most runs have no `toolUseId`). `link` (whole-session) and `attribute` (per-run) are **mutually exclusive per session** (`board.entries_for_session`) so the same spend is never double-counted. Cleaned the dogfood board: the two identical `$450` whole-session/whole-repo lumps on us-13/us-15 are replaced by distinct real per-run attributions. 5 more tests (85 total).

### Fixed
- **Dashboard "Usage over time" chart crash** (`Cannot read properties of null (reading 'getContext')`) — a chart's empty-state overwrote its `<canvas>`, so the next render hit a null canvas. Charts now recreate a fresh canvas in a `data-canvas`-anchored wrap each render; empty-states no longer destroy the canvas.
- **Confusing kanban cost badges** — cards showed two unlabeled epic/feature rollup chips (e.g. `$900.06` on every card of an epic, read as the card's own price). Cards now show one labeled **US cost** line; the Epic/Feature rollups moved to the story modal, labeled.
- **"Usage over time" empty for a single-day project** — a 1-point line draws no segment and `pointRadius` was 0, so the axes auto-scaled to the data but nothing was drawn. Few-point series (≤2 days) now render a visible point.

## [1.2.0] — 2026-06-27

### Added
- **`/fenrir:status` — a Tech Lead Report** (new command, 4 → 5): a deterministic helper (`scripts/techlead_report.py`, stdlib) emits one honest markdown report for a repo — gate health (pre-commit, CI, **branch-protection ARMED/NOT-ARMED verified via `gh api`** with an `--offline` declared-only fallback, `template_version` drift), open gate-exceptions with **self-granted / lapsed flagging**, and an onboarding "how we deliver here". No DORA proxies (a red-team on the spec showed local tags ≠ deploys and `fix:`-ratio ≠ change-failure — those are deferred until a real deploy/incident source exists). 24 tests; helper covered by CI ruff/mypy/pytest (CI + pyproject + pre-commit extended to `scripts/`). Spec at `docs/specs/techlead-status-report.md`.
- **`memory-keeper`: optional `approved_by` on gate-exceptions** — a waiver is *approved* only when `approved_by` is set and `!= granted_by`; otherwise *self-granted* (recorded but flagged unverified by `/fenrir:status`). Additive schema change (the `session-context` SessionStart hook ignores unknown keys); `waive`/`expire` steps and the schema/refusal clauses amended to keep the skill self-consistent.
- **Fenrir now dogfoods its own couche-0** (it shipped a CI gate to consumers but ran none on itself):
  - **`.github/workflows/ci.yml`** — required-check CI on the plugin's own artifacts: JSON manifests + templates parse, YAML parses, every skill has `SKILL.md` + `VERIFY.md` and every agent has frontmatter, plus `py_compile` / `ruff` / `mypy` / `pytest` on `hooks/`.
  - **`hooks/tests/`** — 209 passing pytest cases (subprocess-based, side-effects sandboxed) covering all 9 hooks' deny/ask/allow + malformed-input paths; each case validated against the real hook.
  - **`pyproject.toml`** — governs the first-party `hooks/` Python (ruff high-signal set + mypy + pytest config; `[tool.uv] package = false`).
  - **root `.pre-commit-config.yaml`** — local gate (ruff, gitleaks, conventional-commit, hygiene, pytest-on-push) mirroring what the plugin installs into consumers.
- **Three new skills** (26 → 29): **`alert-delivery`** (wire alert rules → Azure Monitor action groups / Alertmanager receivers / PagerDuty so a page reaches a human), **`load-test`** (k6/Locust/Azure Load Testing scenarios with SLO-aligned thresholds to exercise canary gates pre-prod), **`image-scan`** (Trivy/Grype/Defender base-image CVE scan as a CI required-check failing on HIGH/CRITICAL). Each with `SKILL.md` + `VERIFY.md`, adversarially verified.
- **`LICENSE`** (MIT) — the license was declared in `plugin.json`/README but the file was missing.
- **`CONTRIBUTING.md`** + **`SECURITY.md`** — contribution/gate workflow and a private vulnerability-disclosure policy for a security-focused plugin.
- **`templates/renovate.json`** + **`templates/CODEOWNERS`** — `repo-bootstrap` now copies both from templates instead of hand-generating them (every other couche-0 artifact already had a template; these two were the gap). Renovate policy: patch/minor auto-merge after green required CI, major stays manual; CODEOWNERS ships risk-path owners (`auth/`, `iac/`, `migrations/`, `**/security/`, gate config) with `@your-org/*` placeholders to fill.

### Changed
- **`DELIVERY-SKILLSET.md` translated to English** (was French while every other doc is English; the README links it as the architecture reference). Structure, the couche-0 model, and all identifiers preserved verbatim.
- **Doc counts + agent inventory corrected** — README/PUBLISHING now say **29 skills, 4 commands** (were 26/3); the README Agents row and GETTING-STARTED now list all **8** agents (`context-engineering` was miscategorized as a skill; `security-guardrail` was missing).
- **All 8 agents compressed (~17% fewer characters per body, paid on every invocation)** — terse imperative bullets, dropped prose/repetition. Adversarially verified (8/8 PASS): YAML frontmatter byte-identical and every machine-parseable contract preserved verbatim (`VERDICT:` line, guardrail JSON, `MISSING-MAPPING`/`REFUSED` blocks, `MERGE-READY VERDICT`, the ADR + Context-Plan templates). Zero operating rule dropped.
- **Skill descriptions rebalanced** — thin ones gained concrete trigger phrases (`auth-gen`, `frontend-gen`, `doc-generator`, `security-review`); verbose ones trimmed (`progressive-delivery`, `gitops`, `feature-flags`) by moving mechanism detail into the body. All now in a consistent ~350–580 char band for more even skill routing.
- **`repo-bootstrap`** step 6 now references `templates/renovate.json` and `templates/CODEOWNERS` explicitly.

### Fixed
- **`config-audit` + `content-scanner` hooks** — valid-but-non-object JSON on stdin (`null`/scalar/list) raised an uncaught `AttributeError` and exited non-zero instead of a graceful fail-open no-op; added an `isinstance(data, dict)` guard. Found by the new hook tests.
- **`hooks/.claude/audit/security-events.jsonl`** — a git-tracked runtime audit artifact that shipped to every consumer; removed from tracking and `.gitignore` broadened to `**/.claude/audit/`.
- **`tool-failure-triage`** — corrected a stale docstring claiming `PostToolUseFailure` is "officially undocumented"; it is a documented, supported hook event (wiring unchanged, confirmed correct).
- **`langgraph-workflow`** — a botched global replace from the v1.1.1 namespacing pass had corrupted a sentence to `verify exact class/fenrir:init`; restored to `verify exact class/init`.

## [1.1.1] — 2026-06-27

### Changed
- All Fenrir command references in the docs are now consistently namespaced: `/fenrir:init`, `/fenrir:challenge-me`, `/fenrir:deliver`, `/fenrir:ship` (native `/code-review`, `/security-review`, `/plugin` untouched). The plugin id stays `fenrir`.
- Repository renamed to **`Kdesantiago/Fenrir`** (capital F); install/clone/marketplace references updated. The plugin id (`fenrir`) and marketplace id (`fenrir-marketplace`) are unchanged.

## [1.1.0] — 2026-06-27

### Added
- **`/fenrir:init <project> [services…]` command** — the front door for a brand-NEW repo: scaffolds a clean **uv-workspace monorepo** (one root `uv.lock`, services as members under `src/`), substitutes the project name, writes a partial `org-profile.yaml`, then runs `repo-bootstrap` for the gate. `repo-bootstrap` is now scoped to adding the gate to an *existing* repo.
- **`templates/uv-workspace/`** — a uv-workspace template (virtual root with `[tool.uv] package = false`, `[dependency-groups] dev`, strict ruff/mypy/pytest, `.gitignore`, an example member with a smoke test). Empirically validated: `uv lock` + `uv sync --all-packages --dev` + `pytest --cov=src` (100%) + `ruff` + `mypy --strict` all green.

### Changed (workspace-correct CI — fixes a red-team REDESIGN verdict on `/fenrir:init`)
- **CI templates rewritten to run once at the repo root** (`uv sync --all-packages --dev` + `pytest --cov=src`) instead of a hardcoded `service_a/b/c` per-service matrix that pointed at directories a fresh repo doesn't have — the old matrix (plus per-service `uv.lock` detection and `--all-extras`) made every newly-init'd repo's first CI run red and blocked all merges. `build` is now conditional on a `Dockerfile` (passes for non-container repos); `pip-audit` audits the root `uv.lock`; `checkout` uses `fetch-depth: 0` so the Semgrep baseline resolves.
- **`repo-bootstrap`**: boundary clarified (existing repos; new repos use `/fenrir:init`), now copies `bootstrap-smoke-test.sh` into the repo and skips files `/fenrir:init` already wrote.
- **`.semgrep.yml`** header genericized — no RAG/LLM-specific assumptions; the two `WARNING` relaxations are flagged stack-conditional (promote to `ERROR` if your repo renders Jinja2 to HTML / isn't containerized).

## [1.0.2] — 2026-06-27

### Changed
- **README rewritten for end users** (what Fenrir is, why, install, quick start) — maintainer/internal detail moved to `GETTING-STARTED.md` / `PUBLISHING.md`.
- Removed the last org-specific example references from `.semgrep.yml` rule comments — generic wording only; no rule behavior change.

## [1.0.1] — 2026-06-27

### Changed
- Removed org-specific references from the shipped templates and skills. Example service names are now generic (`src/service_a`/`service_b`/`service_c`) and the default `environments` is `[dev, staging, prod]`. Examples only — no behavioral change.

## [1.0.0] — 2026-06-27

First public release. Renamed from `delivery-standard` to **Fenrir**. Everything below shipped in 1.0.0.

### Added
- **Security layer ported from PAI inspectors → 5 pure-Python hooks** (no bun/node/daemon), wired by `templates/.claude/settings.json`, covering input→tool→output→config:
  - `delivery-guard.py` (PreToolUse) — denies `--no-verify`, **secret-exfil** (outbound cmd + credential token, pipe-to-shell), **zero-access paths** (`.env`/`.ssh`/`id_rsa`/keys); asks on force-push-to-protected / gate-file edits.
  - `prompt-guard.py` (UserPromptSubmit) — blocks security-override / injection prompts; warns on two-phase exfil.
  - `content-scanner.py` (PostToolUse web) — warns on prompt-injection in fetched content.
  - `config-audit.py` (PostToolUse) — audit trail of `.claude/settings.json` changes (flags sensitive keys).
  - `session-context.py` (SessionStart) — injects the active delivery contract + open gate-exceptions every session.
  - All denies/warns append to `.claude/audit/security-events.jsonl`; fail-open except hard denies.
- **`memory-keeper` skill — in-repo, git-tracked delivery-memory**: decisions, `gate-exceptions.jsonl` (owner + mandatory expiry; the SessionStart hook surfaces open ones), `drift-log.jsonl`, `lessons.md`. Scoped to delivery; stores no secrets/personal data.
- **AKS + Azure Web App platforms**: `org-profile.yaml` `platform` adds `aks` | `webapp`; `iac-gen` branches (AKS: workload-identity + AGIC/app-routing + ACR + Azure CNI; Web App: `azurerm_linux_web_app` + App Service plan + staging slots, no k8s).
- **`stack-adapter` agent + `stack-interface.yaml` manifest** — adapts to enterprise Azure wrappers: the manifest declares the company's CLI/IaC/registry/deploy commands; the agent translates standard ops into them (never guesses; refuses raw `az` when a wrapper is declared). Generators consult it.
- **`/fenrir:ship` now runs the automated pre-PR review** (native `/code-review` + `reviewer` verdict) and refuses to open a known-BLOCK PR.
- **`api-first` skill** — contract-first HTTP APIs: OpenAPI 3.1 spec as source of truth, enforced REST conventions (resources/verbs/status, RFC 9457 errors, versioning, pagination, idempotency), Spectral lint, framework-driven codegen, and Schemathesis/Dredd contract tests (optional `api-contract` CI gate). Refuses to write endpoints absent from the spec.
- **`/fenrir:challenge-me <context>` command** — the front door: adversarially interrogates a raw idea (steelman, real-problem-vs-solution, MVP cut, decisive forks via AskUserQuestion, "don't build / buy instead" allowed), writes a red-teamed spec to `docs/specs/` + records decisions to delivery-memory, then routes deterministically through `repo-bootstrap` → generators (`api-first`/`iac-gen`/…) → `architect` → `/fenrir:deliver` → `/fenrir:ship`. Never scaffolds before challenging.
- **`cronjob` skill** — platform-correct scheduled jobs (`aks`/`k8s`→CronJob, `webapp`/`serverless`→Azure timer/Container Apps job, `vm`→systemd timer) with mandatory reliability defaults: no double-run (`concurrencyPolicy`), timeout, bounded backoff, missed-run handling, failure + dead-man's-switch alerting, and a stated idempotency strategy. Refuses a state-mutating job with no idempotency plan.
- **`templates/.semgrep.yml`** — curated SAST ruleset: 14 ERROR (blocking) + 2 WARNING (advisory, excluded by `--severity ERROR`). `0.0.0.0` bind and bare-Jinja2 are WARNING (false-positive on containerized/LLM-prompt code); the narrow autoescape-disabled rule stays ERROR.
- **Concrete `template_version` compatibility check** in `delivery-gates` — reads `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, compares semver (major-match, 0.x minor-match) to `org-profile.yaml`, fails loud on mismatch. Replaces the prose.
- `red-team-destroyer` now ends with `VERDICT: SHIP | FIX-FIRST | REDESIGN` + steelman/HARD-SOFT-ASSUMPTION rules; wired into `/fenrir:deliver` as a pre-code stage against the ADR (REDESIGN = BLOCK).
- `GETTING-STARTED.md` (solo walkthrough) + this `CHANGELOG.md`.

### Changed / Fixed (red-team iteration 3, verified against the real uv/3.12 monorepo)
- **`marketplace.json` `source` set to `"./"`** — plugin sources resolve relative to the marketplace root (the dir containing `.claude-plugin/`), which is the repo root; confirmed with `claude plugin validate` (an earlier `"../"` attempt was wrong and rejected by the validator).
- **CI templates uv-aware + Python 3.12** (was 3.13, which aborts install on services pinned `>=3.12,<3.13`): `uv sync`/`uv run pytest` when `uv.lock` present; triggers `dev`/`main`/`release/*`; added `pip-audit` dependency audit; merged coverage into the `test` job (no duplicate full pytest run).
- `branch-protection.tf` required checks `test/sast/build` (coverage folded into `test`).
- `repo-bootstrap` now: copies `.semgrep.yml` to repo root, detects `uv.lock`, **preserves an existing pipeline** instead of overwriting, installs the in-session guard, installs all three pre-commit hook types incl. `commit-msg`.
- `bootstrap-smoke-test.sh`: matches singular `azure-pipeline.yml`, asserts `.semgrep.yml` present when sast runs, Azure-path checks the blocking build-validation policy (not stage names), `commit-msg` hook detected via `--hook-type=` sentinel.

### Fixed (red-team iteration 6 — executed against the new surface)
- **`FileChanged` matcher `*.tf` was dead** — the matcher takes LITERAL basenames, not globs, so `iac-watch.py` never fired. Now watches `main.tf|variables.tf|outputs.tf|versions.tf|providers.tf|terraform.tfvars`.
- **`.mcp.json` langfuse package `@langfuse/mcp-server` doesn't exist** → silent npx failure for every user. Changed to `langfuse-mcp`. (MCP servers auto-start when the plugin is enabled and need their env: `AZURE_SUBSCRIPTION_ID`, `LANGFUSE_*` — they fail gracefully if unset.)
- **`tool-failure-triage.py` crashed** (`TypeError: unhashable type`) on a non-string `tool_name`; now coerces to str and reads `error` as a fallback field.
- **`session-end.py` dropped the whole summary** on a single corrupt ledger line; now per-line `try/except`.
- **`aks-deploy-watch.sh` hung forever** (`tail -F & … wait`) when `DS_ERROR_LOG` was set, and ignored a `DS_KUBECTL` wrapper-with-args; now traps+kills the tail, drops the `wait`, `read -ra` splits the wrapper, `sed -u` for live lines, 20-min cap corrected.
- **`obs_backend` mismatch** — progressive-delivery/error-budget keyed off `prometheus`/`azure-monitor`, not in the enum; added both to `org-profile.yaml obs_backend`.
- **observability-gen didn't author SLI/SLO/alert rules** that progressive-delivery, error-budget, and incident-runbook delegate to it; extended it to do so (the delegations were dead).
- **`deploy-watch` dangling reference** in incident-runbook → `aks-deploy-watch`. **`container_registry`** + **`environments`** added to `org-profile.yaml` (gitops/feature-flags referenced keys that didn't exist; feature-flags no longer hardcodes `dev/staging/prod`).
- **Rollout "both canary AND blue-green"** is invalid (Argo strategy is exclusive) → progressive-delivery now emits ONE strategy + states the in-cluster-controller prerequisite.
- Reciprocal NOT-clauses added (delivery-gates↔error-budget, llm-gen↔online-llm-eval); online-llm-eval drops the unwired `PostToolUse` hook claim (only `Stop` is wired); VERIFY commands hardened against empty `$(...)` false-OK.
- delivery-guard branch-guard resolves the branch once (was two `git symbolic-ref` calls per commit).

### Added (lifecycle skills + Claude Code plugin primitives — from a cited deep-research gap analysis)
- **AKS delivery-loop skills**: `progressive-delivery` (Argo Rollouts/Flagger canary+blue-green + metric-gated promote/rollback), `gitops` (Flux v2/Argo CD pull-based, AKS cluster-extension, CI/CD split), `feature-flags` (Azure App Configuration flighting — release≠deploy, kill-switch).
- **Ops skills**: `incident-runbook` (Azure WAF OE:08 incident-response plan + recovery playbooks), `error-budget` (SRE 4-week error-budget freeze wired as a CI gate).
- **`online-llm-eval` skill** — production-traffic LLM-as-judge via Langfuse (+ RAGAS), complementing llm-gen's offline golden-set.
- **Previously-unused Claude Code plugin primitives now used** (schemas verified against code.claude.com/docs): bundled MCP servers (`.mcp.json`: Azure + Langfuse), bundled LSP (`.lsp.json`: pyright), background **Monitors** (`monitors/`: AKS rollout-watch + error-log tail, started on skill-invoke), and 3 new hook events — `PostToolUseFailure` (failure trail+triage), `SessionEnd` (delivery-memory housekeeping), `FileChanged(*.tf)` (reactive terraform-fmt/YAML check).
- **Opt-in prompt/agent-type hooks** (`templates/optional-hooks.json` + `security-guardrail` agent): a `prompt`-type Stop quality-judge and an `agent`-type UserPromptSubmit LLM guardrail (cost per event → opt-in).
- **Org distribution** (`templates/team-settings.json`): `extraKnownMarketplaces` + `enabledPlugins` so trusting a repo auto-prompts teammates to install the pinned plugin — closes the cross-repo consumption gap.
- Note (DORA 2024, cited): golden paths shipped as **defaults, not mandates** (exclusive-platform mandates measurably cut throughput); measure DORA rather than forcing exclusive use.

### Added (delivery + quality + LLM-app skills, branch/doc hooks)
- **Delivery skills**: `release` (semver bump + tag + CHANGELOG→release notes via gh/az), `db-migration` (safe Alembic: reversible, lock-free, backfill-separate, tested up→down→up), `secrets` (manage via Key Vault/SOPS + rotation, ≠ scanning), `deps` (supply-chain: license allowlist + uv.lock pinning + cosign provenance + Renovate auto-merge policy).
- **`quality-master` skill** — the strict/expert quality tier (distinct from delivery-gates which runs tooling): strict mypy, broad ruff, Hypothesis property-based pytest + per-package coverage; ratchets up only.
- **LLM-app-dev pack** (product-building, a concern distinct from couche-0 delivery): `langgraph-workflow` (typed-State graph: nodes, routing, checkpointer, interrupts, retries), `retriever` (RAG: chunking, embeddings, vector-store adapter, hybrid search + rerank, recall@k eval), `llm-cost-monitor` (token/cost attribution + budget alerts via obs_backend, scoped to monitoring — accounting stays in llm-gen), `context-engineering` agent (designs the context window + writes versioned prompts).
- **`branch-guard`** (in `delivery-guard.py`): `ask` on `git commit`/`git push` directly on a protected branch (main/master/release*) → enforces branch-per-change.
- **`doc-staleness` Stop hook**: if code changed but CHANGELOG.md didn't, blocks the stop ONCE and nudges to run doc-keeper — the deterministic backstop behind "docs always up to date". Loop-safe via `stop_hook_active`.
- **KISS/DRY review lens** added to `reviewer` (PR-hygiene rule) and `red-team-destroyer` (attack dimension 11): flags over-engineering + duplication.
- **org-profile** += optional `vector_store` (pgvector | azure-ai-search | qdrant | weaviate | none) for the `retriever` skill.

### Added (profile values + docs agent)
- **`doc-keeper` agent** — keeps docs true to the code: on a diff it updates `CHANGELOG.md` (conventional-commit→Keep-a-Changelog mapping), the affected README(s), and API docs, and runs a stale-reference pass (flags docs naming a file/skill/flag that no longer exists). Wired into `/fenrir:deliver` and `/fenrir:ship` (runs before the review, so the changelog reviewer requires already exists) → docs stay current on every delivery. Complements the `doc-generator` skill (conventions) by APPLYING them to a specific change.
- **org-profile values**: `obs_backend` += `langfuse` (LLM tracing/evals — `observability-gen` wires it over OTLP/SDK, pairs with `llm-gen`); `llm_provider` += `azure` (Azure OpenAI Service — `llm-gen` uses `AzureOpenAI`/`azure_endpoint`/`api_version`/deployment, AAD or key auth); `front` += `html` (plain static — `frontend-gen` emits semantic HTML + vanilla CSS/JS, no build step).

### Security hardening (red-team iteration 4 — bypasses found by EXECUTING the hooks)
- **delivery-guard.py — fail-closed + real bypass coverage.** A list-typed `command` (`["git","commit","--no-verify"]`) used to throw → fail-OPEN allow; now mutating tools fail CLOSED (deny) on any unparseable input, and `command`/`file_path` are coerced to str. Added: `cat .env`/secret-file access via Bash (not just Read), gate-bypass beyond `--no-verify` (`commit -n`, `core.hooksPath`, `HUSKY=0`, `ci.skip`, `git config hooksPath`), `re.IGNORECASE`, secret-exfil by indirection (env-var/`$(…)`/file source + outbound), non-HTTP channels (`scp`/`rsync`/`aws s3`/`gsutil`/`kubectl get secret`), more token shapes (JWT/Azure-SAS/GCP/PAT), force-push incl. `+refspec`/flag-less, `NotebookEdit`. Gate-file **kill switch** (`.claude/hooks/`, `.claude/settings*.json`) is now `deny`, not `ask`. `.env.example`/`.sample` excluded.
- **prompt-guard.py + content-scanner.py** — the canonical "ignore all previous instructions" no longer slips through (the old regex required exactly one word); broadened patterns, NFKC normalization (homoglyph/width), benign-object guard, MCP web/fetch tools now scanned.
- **session-context.py** — quote-aware YAML parse (`#` inside quotes preserved, nested/empty keys skipped), `yaml.safe_load` when available; gate-exception expiry parsed as ISO `YYYY-MM-DD` with missing/unparseable treated as **expired** (was a raw string compare that dropped valid US-format waivers and kept malformed ones).
- **config-audit.py** — now also audits `settings.local.json` (the override an attacker would use); audit-write failures warn on stderr.
- **stack-interface.yaml flattened** (`iac_backend_config` nested map → top-level keys) so the SessionStart parser doesn't drop/inject empty keys; added `func_deploy_cmd`/`vm_systemd_apply_cmd`; softened "enforces" → best-effort (real block = CI denylist).
- **api-first** — added missing `templates/ci/api-contract.yml` + `templates/api/.spectral.yaml` (the contract gate was a dead reference); refuses `framework: streamlit|none`; softened the unenforceable "refuses endpoints" claim.
- **cronjob** — concrete dead-man's-switch per `obs_backend`; routes through `stack-adapter` only for ops with a wrapper, emits non-cloud ops (systemd/func) directly on `MISSING-MAPPING`.
- **challenge-me** — description fenced vs `architect`; hard cap of 2 question rounds; "optional hard gate" contradiction removed.

### Pending (next release)
- Externalize the security ruleset to an optional `.claude/delivery-security.json` override (currently hardcoded in the hooks; fine as-is, but org-tunable would help) + a CI mirror of the protected-path scan (PAI adoption #4 — in-session is done via `delivery-guard.py`).
- Per-skill `VERIFY.md` harness with blocking/informational split (PAI adoption #7).
- `azuredevops_build_definition` resource in `azure-branch-policy.tf` so the gate can self-arm (RT #8).
- AKS/Web App reference IaC stubs under `templates/iac/` (iac-gen currently describes the branches; shipping starter charts/Bicep would speed first use).

## [0.1.0] — initial design

### Added
- 3-layer architecture: **skills** (capabilities) + **subagents** (personas) + **commands** (orchestration), over a **couche-0 infra** gate.
- Skills: `repo-bootstrap`, `delivery-gates`, `security-review`, `doc-generator`, and 5 profile-driven generators (`iac-gen`, `auth-gen`, `observability-gen`, `frontend-gen`, `llm-gen`).
- Subagents: `architect`, `qa-tester`, `reviewer`, `red-team-destroyer`.
- Commands: `/fenrir:deliver` (deterministic light/full routing), `/fenrir:ship`.
- Couche-0 templates: `org-profile.yaml`, `.pre-commit-config.yaml`, GitHub + Azure CI + branch-protection, `scripts/bootstrap-smoke-test.sh`.
- `plugin.json` + `marketplace.json`.
- Design rationale + red-team teardowns: `DELIVERY-SKILLSET.md`.

### Core principle
- A skill cannot enforce; the real gate is deterministic infra (hooks + CI + branch-protection). Generators refuse on stack mismatch.
