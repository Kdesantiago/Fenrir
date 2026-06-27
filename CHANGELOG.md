# Changelog

All notable changes to `fenrir`. Format: [Keep a Changelog](https://keepachangelog.com/), [SemVer](https://semver.org/).

## [Unreleased]

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
- **`/ship` now runs the automated pre-PR review** (native `/code-review` + `reviewer` verdict) and refuses to open a known-BLOCK PR.
- **`api-first` skill** — contract-first HTTP APIs: OpenAPI 3.1 spec as source of truth, enforced REST conventions (resources/verbs/status, RFC 9457 errors, versioning, pagination, idempotency), Spectral lint, framework-driven codegen, and Schemathesis/Dredd contract tests (optional `api-contract` CI gate). Refuses to write endpoints absent from the spec.
- **`/challenge-me <context>` command** — the front door: adversarially interrogates a raw idea (steelman, real-problem-vs-solution, MVP cut, decisive forks via AskUserQuestion, "don't build / buy instead" allowed), writes a red-teamed spec to `docs/specs/` + records decisions to delivery-memory, then routes deterministically through `repo-bootstrap` → generators (`api-first`/`iac-gen`/…) → `architect` → `/deliver` → `/ship`. Never scaffolds before challenging.
- **`cronjob` skill** — platform-correct scheduled jobs (`aks`/`k8s`→CronJob, `webapp`/`serverless`→Azure timer/Container Apps job, `vm`→systemd timer) with mandatory reliability defaults: no double-run (`concurrencyPolicy`), timeout, bounded backoff, missed-run handling, failure + dead-man's-switch alerting, and a stated idempotency strategy. Refuses a state-mutating job with no idempotency plan.
- **`templates/.semgrep.yml`** — curated SAST ruleset: 14 ERROR (blocking) + 2 WARNING (advisory, excluded by `--severity ERROR`). `0.0.0.0` bind and bare-Jinja2 are WARNING (false-positive on containerized/LLM-prompt code); the narrow autoescape-disabled rule stays ERROR.
- **Concrete `template_version` compatibility check** in `delivery-gates` — reads `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, compares semver (major-match, 0.x minor-match) to `org-profile.yaml`, fails loud on mismatch. Replaces the prose.
- `red-team-destroyer` now ends with `VERDICT: SHIP | FIX-FIRST | REDESIGN` + steelman/HARD-SOFT-ASSUMPTION rules; wired into `/deliver` as a pre-code stage against the ADR (REDESIGN = BLOCK).
- `GETTING-STARTED.md` (solo walkthrough) + this `CHANGELOG.md`.

### Changed / Fixed (red-team iteration 3, verified against the real Suez uv/3.12 monorepo)
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
- **`deploy-watch` dangling reference** in incident-runbook → `aks-deploy-watch`. **`container_registry`** + **`environments`** added to `org-profile.yaml` (gitops/feature-flags referenced keys that didn't exist; feature-flags no longer hardcodes `dev/hml/prod`).
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
- **`doc-keeper` agent** — keeps docs true to the code: on a diff it updates `CHANGELOG.md` (conventional-commit→Keep-a-Changelog mapping), the affected README(s), and API docs, and runs a stale-reference pass (flags docs naming a file/skill/flag that no longer exists). Wired into `/deliver` and `/ship` (runs before the review, so the changelog reviewer requires already exists) → docs stay current on every delivery. Complements the `doc-generator` skill (conventions) by APPLYING them to a specific change.
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
- Commands: `/deliver` (deterministic light/full routing), `/ship`.
- Couche-0 templates: `org-profile.yaml`, `.pre-commit-config.yaml`, GitHub + Azure CI + branch-protection, `scripts/bootstrap-smoke-test.sh`.
- `plugin.json` + `marketplace.json`.
- Design rationale + red-team teardowns: `DELIVERY-SKILLSET.md`.

### Core principle
- A skill cannot enforce; the real gate is deterministic infra (hooks + CI + branch-protection). Generators refuse on stack mismatch.
