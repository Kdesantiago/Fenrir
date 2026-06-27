# 🐺 Fenrir

> The wolf that guards your delivery — an org-portable Claude Code plugin (plugin id: `fenrir`) that **standardizes code delivery across all repos**: a coordinated pack of 26 skills, 8 subagents, and 9 hooks behind one deterministic gate.

**New here? → [GETTING-STARTED.md](GETTING-STARTED.md) (solo, 10 min, end to end).**

Design rationale + red-team teardown: [DELIVERY-SKILLSET.md](DELIVERY-SKILLSET.md). Changes: [CHANGELOG.md](CHANGELOG.md).

## The one idea that makes it work

**A skill cannot enforce anything** — it is advisory text the model may skip. So the real gate is **deterministic infra** (git hooks + CI required-checks + branch-protection-as-code). Skills give fast feedback; infra blocks. Everything below respects that split.

## Layout

```
.claude-plugin/plugin.json   # manifest
skills/                      # capabilities (advisory feedback + profile-driven generators)
  repo-bootstrap/            # installs couche-0 infra (the real gate)
  delivery-gates/            # advisory local runner of existing checks
  security-review/           # wraps native /security-review (SAST/SBOM/threat)
  doc-generator/             # aggregates existing docs (no ADR — that's architect)
  iac-gen/ auth-gen/ observability-gen/ frontend-gen/ llm-gen/   # profile-driven generators (iac-gen: aks/webapp/k8s/…)
  api-first/                # OpenAPI contract-first: REST conventions + codegen + contract tests
  cronjob/                  # platform-correct scheduled jobs with reliability defaults
  memory-keeper/            # in-repo delivery-memory (decisions, gate-exceptions, drift, lessons)
  release/                  # semver bump + tag + CHANGELOG→release notes (GH/Azure)
  db-migration/             # safe Alembic migrations (reversible, lock-free, tested up→down)
  secrets/                  # manage secrets via Key Vault/SOPS (≠ scanning)
  deps/                     # supply-chain: license policy + pinning + provenance + Renovate
  quality-master/           # strict mypy + broad ruff + Hypothesis pytest (ratchets up)
  langgraph-workflow/ retriever/ llm-cost-monitor/   # LLM-app-dev pack (product-building)
  progressive-delivery/ gitops/ feature-flags/        # AKS delivery loop (Argo Rollouts/Flux/App Config)
  incident-runbook/ error-budget/                     # ops: incident plan + SRE error-budget freeze
  online-llm-eval/                                     # prod-traffic LLM-as-judge (Langfuse)
agents/                     # personas (isolated context)
  architect/ qa-tester/ reviewer/ red-team-destroyer/ stack-adapter/ doc-keeper/ context-engineering/
  security-guardrail/        # LLM guardrail for the opt-in agent-type hook
commands/                   # orchestration
  challenge-me/             # idea → challenged+scoped spec → drives the build skills
  deliver/ ship/            # ship/ runs the automated pre-PR LLM review
hooks/                      # in-session enforcement + security (couche 0, agent-side; pure Python stdlib)
  delivery-guard.py         # PreToolUse: deny --no-verify/secret-exfil/zero-access, ask on gate-file/branch-protected commits
  prompt-guard.py           # UserPromptSubmit: prompt-injection scan
  content-scanner.py        # PostToolUse(web): injection-in-fetched-content warning
  config-audit.py           # PostToolUse: audit trail of .claude/settings.json changes
  session-context.py        # SessionStart: inject active delivery contract + open gate-exceptions
  doc-staleness.py          # Stop: nudge to sync CHANGELOG when code changed but docs didn't
  tool-failure-triage.py    # PostToolUseFailure: failure trail + triage hint
  session-end.py            # SessionEnd: finalize delivery-memory (counts open/expired waivers)
  iac-watch.py              # FileChanged(*.tf): reactive terraform-fmt / YAML check
.mcp.json                   # bundled MCP servers (Azure, Langfuse) — live deploy/trace/eval data
.lsp.json                   # bundled LSP (pyright) — Python code intelligence
monitors/                   # background Monitors (AKS rollout watch, error-log tail; start on skill-invoke)
templates/                  # couche-0 infra the generators/bootstrap emit
  org-profile.yaml  stack-interface.yaml  .pre-commit-config.yaml  .semgrep.yml
  branch-protection.tf  azure-branch-policy.tf
  ci/required-checks.yml  ci/azure-pipelines.yml  ci/api-contract.yml
  api/.spectral.yaml        # api-first REST-convention lint ruleset
  .claude/settings.json     # wires all 8 hook events into consuming repos
  optional-hooks.json       # opt-in prompt/agent-type LLM-as-judge + guardrail (cost per event)
  team-settings.json        # org distribution: extraKnownMarketplaces + enabledPlugins (auto-install)
scripts/bootstrap-smoke-test.sh   # proves the gate is wired
```

## Three sub-products (different owners, different cadence)

| Module | What | Primitive |
|---|---|---|
| **A. INFRA (couche 0)** | repo-template + hooks + CI + branch-protection. The real gate. | deterministic files |
| **B. Generators** | profile-driven scaffolds, refuse on stack mismatch | skills reading `org-profile.yaml` |
| **C. Orchestration** | subagents + `/deliver` + `/ship` | subagents + commands |

## Install

> Replace `OWNER` with your GitHub account/org and `fenrir` with the
> repo name if you rename it. The marketplace name (`fenrir-marketplace`)
> comes from `.claude-plugin/marketplace.json` and is what you install against.

```bash
# 1. Add this repo as a marketplace, PINNED to a released tag (not a moving branch).
/plugin marketplace add OWNER/fenrir@v1.0.0
#    …or full git URL (GitLab/Bitbucket/self-hosted) — pin with #ref:
#    /plugin marketplace add https://github.com/OWNER/fenrir.git#v1.0.0

# 2. Install the plugin from that marketplace.
/plugin install fenrir@fenrir-marketplace

# 3. (later) Move to a new release: re-point the marketplace at the new tag, then update.
#    /plugin marketplace add OWNER/fenrir@v0.2.0
#    /plugin marketplace update fenrir-marketplace
#    /plugin update fenrir@fenrir-marketplace
```

Local dev (test uncommitted changes without publishing):

```bash
claude --plugin-dir /absolute/path/to/fenrir   # then /reload-plugins after edits
```

Never copy individual files into per-repo `~/.claude` — that guarantees drift. Consume the **pinned plugin version**.

### Publishing this repo as the marketplace remote (one-time)

```bash
git init && git add -A && git commit -m "fenrir plugin + marketplace v1.0.0"
git branch -M main
git remote add origin git@github.com:OWNER/fenrir.git
git push -u origin main
git tag -a v1.0.0 -m "fenrir v1.0.0"   # tag MUST match plugin.json "version"
git push origin v1.0.0
claude plugin validate .                           # checks marketplace.json + version match
```

The git tag pins the *catalog*; `plugin.json`'s `version` pins the *plugin*. Bump `version` on every release, then tag `vX.Y.Z` to match — pushing commits without bumping does nothing for installed users.

### Org-wide auto-install (no manual `/plugin install` per dev)

Commit `templates/team-settings.json` as a repo's `.claude/settings.json` (merge into an existing one). When a teammate trusts the project folder, Claude Code reads `extraKnownMarketplaces` + `enabledPlugins` and **auto-prompts them to install the pinned plugin** — the standardized cross-repo consumption model. Edit `OWNER/fenrir` to your marketplace repo.

## Stack note (read before bootstrapping)

Couche-0 ships **both** GitHub (`templates/ci/required-checks.yml`, `templates/branch-protection.tf`) and **Azure DevOps** (`templates/ci/azure-pipelines.yml`, `templates/azure-branch-policy.tf`) variants. `repo-bootstrap` picks by your CI provider — install the one your repo actually uses, never the other. After bootstrap, run `scripts/bootstrap-smoke-test.sh` to prove the gate is wired (hooks installed, CI job names == required checks, terraform valid).

All agents use `model: inherit` for portability across plans; pin a model only if you have a hard requirement.

## Per-repo setup

1. Run `repo-bootstrap` → writes `org-profile.yaml`, installs hooks, CI workflow, branch-protection.
2. `terraform apply` the branch-protection (this arms the real gate).
3. Edit `org-profile.yaml` to declare your stack — generators refuse without it.

## Recommended rollout order

1. Couche 0 INFRA + `repo-bootstrap` (the mandate)
2. `org-profile.yaml` + one pilot generator on your current stack
3. `delivery-gates` + `security-review`
4. `architect` + `qa-tester` subagents
5. `/deliver` + `/ship`
6. release / supply-chain / secrets primitives

## Reusable across projects

- `agents/red-team-destroyer` — drop into any repo to get a ruthless adversarial review of a design, PR, or codebase.
- All generators are profile-driven, so the same plugin serves every future project once its `org-profile.yaml` is set.
