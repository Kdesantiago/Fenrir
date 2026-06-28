# Publishing & Using `fenrir`

Self-contained guide: how to put this plugin on a Claude Code marketplace, distribute it across your org, and use it. No other file required to follow this.

> **What this is.** `fenrir` is a Claude Code **plugin** (30 skills, 9 subagents, 5 commands, 9 hooks, bundled MCP/LSP/Monitors) that standardizes the whole delivery lifecycle — from `/fenrir:challenge-me <idea>` through scaffolding, gates, progressive delivery on AKS, and LLM-app evals. **This repository is itself the marketplace** (it ships `.claude-plugin/marketplace.json`), so publishing = pushing this repo to git and tagging a release.

---

## 0. Prerequisites

| Need | For |
|---|---|
| `git` + a remote (GitHub / Azure Repos / GitLab) | hosting the marketplace |
| Claude Code (CLI or app) | installing/using the plugin |
| `node`/`npx` | the bundled MCP servers (Azure, Langfuse) |
| `pip install pyright` (or `npm i -g pyright`) | the bundled Python LSP (optional) |
| `python3`, `pre-commit`, `terraform`, `gh`/`az` | when a consumer runs the gate (per-repo, not for publishing) |

Plugin identity (do not rename casually — install commands depend on it):
- **Marketplace name:** `fenrir-marketplace` (from `.claude-plugin/marketplace.json`)
- **Plugin name:** `fenrir` (from `.claude-plugin/plugin.json`)
- **Version:** the `version` field in `.claude-plugin/plugin.json` (e.g. `1.0.0`) — this is the pin.

---

## 1. Publish the marketplace (one-time)

This repo already contains the two manifests that make it a valid marketplace:
- `.claude-plugin/marketplace.json` — the catalog (lists the plugin; `source: "./"` — plugin sources resolve relative to the **marketplace root**, i.e. the directory that contains `.claude-plugin/`, which is the repo root = the plugin root).
- `.claude-plugin/plugin.json` — the plugin manifest (name, version, components).

Validate, then push and tag:

```bash
# from the repo root
claude plugin validate .                 # checks marketplace.json + plugin.json schema & version

git init                                 # skip if already a repo
git add -A
git commit -m "fenrir plugin + marketplace v1.0.0"
git branch -M main

# create an empty repo on your host first, then:
git remote add origin git@github.com:OWNER/Fenrir.git
git push -u origin main

# tag the release — the tag MUST match plugin.json "version"
git tag -a v1.0.0 -m "fenrir v1.0.0"
git push origin v1.0.0
```

Replace `OWNER` with your GitHub org/user (or use your Azure Repos / GitLab URL).

**How the pin works** (read once, saves confusion):
- The **git tag** (`v1.0.0`) pins the *catalog* — consumers add the marketplace at that ref.
- `plugin.json`'s **`version`** pins the *plugin* — that string is what an installed user is on.
- Together they make a release immutable. The marketplace entry intentionally does **not** also set a version (a double-pin would mask `plugin.json`).

---

## 2. Install it (a single developer)

In any Claude Code session:

```bash
# 1. Add this repo as a marketplace, PINNED to the released tag.
/plugin marketplace add OWNER/Fenrir@v1.0.0
#    …or a full git URL (Azure Repos / GitLab / self-hosted), pin with #ref:
#    /plugin marketplace add https://github.com/OWNER/Fenrir.git#v1.0.0

# 2. Install the plugin from that marketplace.
/plugin install fenrir@fenrir-marketplace
```

Local development (test uncommitted changes, no marketplace, no install):

```bash
claude --plugin-dir /absolute/path/to/fenrir   # then /reload-plugins after edits
```

Never copy individual skill/hook files into a per-repo `~/.claude` — that drifts. Always consume the pinned plugin.

---

## 3. Distribute org-wide (auto-prompt every teammate)

So nobody runs `/plugin install` by hand: commit `templates/team-settings.json` as a repo's **`.claude/settings.json`** (merge into an existing one). Edit `OWNER`:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "extraKnownMarketplaces": {
    "fenrir-marketplace": {
      "source": { "source": "github", "repo": "OWNER/Fenrir" }
    }
  },
  "enabledPlugins": {
    "fenrir@fenrir-marketplace": true
  }
}
```

When a teammate clones the repo and trusts the folder, Claude Code reads these keys and **auto-prompts them to install the pinned plugin**. This is the standardized cross-repo consumption model — the plugin's whole point.

---

## 4. Use it — bootstrap a repo to the standard

Once installed, in a target repo ask Claude Code:

> "bootstrap this repo to the delivery standard"

The `repo-bootstrap` skill then installs **couche 0 — the real gate** (idempotently):
1. Writes `org-profile.yaml` (declare your stack — see §5).
2. Installs `pre-commit` hooks (commit + push + commit-msg) and the 9 in-session `.claude/hooks/*.py`.
3. Drops the CI required-checks workflow (GitHub `required-checks.yml` or Azure `azure-pipelines.yml`) and `.semgrep.yml`.
4. Drops branch-protection-as-code (`branch-protection.tf` / `azure-branch-policy.tf`).

Then **arm the gate and verify it**:

```bash
terraform apply              # branch-protection — the ONLY thing that truly blocks a non-conforming merge
bash scripts/bootstrap-smoke-test.sh   # proves hooks installed, CI job names == required checks, .semgrep.yml present
```

> **Mental model:** *skills advise, infra enforces.* A skill is text the agent can skip; the block is pre-commit + the in-session `delivery-guard` hook + CI required-checks + branch-protection. Bootstrap + `terraform apply` is what makes delivery non-optional.

---

## 5. Declare your stack — `org-profile.yaml`

Generators **refuse on mismatch** rather than emit wrong-stack code. Edit the file `repo-bootstrap` created:

```yaml
platform: aks            # aks | webapp | k8s | serverless | vm | ecs
framework: fastapi       # fastapi | express | spring | streamlit | none
auth_provider: entra     # entra | okta | keycloak | auth0 | none
obs_backend: grafana     # grafana | prometheus | azure-monitor | datadog | cloudwatch | honeycomb | langfuse
llm_provider: azure      # anthropic | openai | azure | bedrock | vertex | none
front: html              # react | vue | svelte | streamlit | html | none
vector_store: pgvector   # pgvector | azure-ai-search | qdrant | weaviate | none
container_registry: ""   # e.g. mycorp.azurecr.io (or declare in stack-interface.yaml)
environments: [dev, staging, prod]
template_version: "1.0.0"
```

Enterprise Azure wrappers? Also copy `templates/stack-interface.yaml` → repo root and fill it; the `stack-adapter` agent then emits your wrapper commands instead of raw `az`.

---

## 6. Use it — daily

**Start from an idea** (the front door):
> `/fenrir:challenge-me build an internal RAG assistant for X` — it challenges the idea, writes a scoped spec, then drives the build skills.

**Orchestrated delivery:**
> `/fenrir:deliver add endpoint Y` → architect → coder → qa-tester → doc-keeper → review → gates → PR (light/full by diff size).
> `/fenrir:ship` → runs the automated pre-PR review, opens the PR, surfaces CI status.

**Ask for a skill by intent** (examples):
| Want | Say |
|---|---|
| Init the gate | "bootstrap this repo" → `repo-bootstrap` |
| Contract-first API | "design the API for X" → `api-first` |
| Safe DB migration | "add a migration for X" → `db-migration` |
| Canary on AKS | "set up progressive delivery" → `progressive-delivery` |
| GitOps loop | "wire Flux GitOps" → `gitops` |
| Cut a release | "release this" → `release` |
| Incident plan | "write the incident runbook" → `incident-runbook` |
| Prod LLM eval | "score production LLM traffic" → `online-llm-eval` |

**Subagents** (delegated): `architect`, `qa-tester`, `reviewer`, `red-team-destroyer` ("red-team this"), `stack-adapter`, `doc-keeper`, `context-engineering`.

**Bundled live tools** (activate when their env is set):
- MCP `azure` → set `AZURE_SUBSCRIPTION_ID`. MCP `langfuse` → set `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`. (They fail gracefully if unset.)
- LSP `pyright` → install the binary (`pip install pyright`).
- Monitors (`aks-deploy-watch`) start when you invoke `progressive-delivery` / `incident-runbook`; set `DS_K8S_DEPLOYMENT` (and `DS_KUBECTL` if you use a wrapper).

**Opt-in LLM hooks** (cost a token call per event): merge `templates/optional-hooks.json` into the plugin's `hooks/hooks.json` or a repo's settings to enable the `prompt`-type Stop quality-judge and the `agent`-type `security-guardrail`.

---

## 7. Release a new version

1. Make changes; let `doc-keeper` (or you) update `CHANGELOG.md` under `[Unreleased]`, or run the `release` skill which does the rest:
2. Bump `version` in `.claude-plugin/plugin.json` (semver: feat→minor, fix→patch, breaking→major).
3. Move `[Unreleased]` → a dated `[X.Y.Z]` section in `CHANGELOG.md`.
4. Commit, then tag and push:

```bash
git commit -am "release vX.Y.Z"
git tag -a vX.Y.Z -m "fenrir vX.Y.Z"
git push origin main vX.Y.Z
```

Consumers move up by re-pointing the marketplace at the new tag and updating:

```bash
/plugin marketplace add OWNER/Fenrir@vX.Y.Z
/plugin marketplace update fenrir-marketplace
/plugin update fenrir@fenrir-marketplace
```

> **Important:** pushing commits **without** bumping `plugin.json`'s `version` does nothing for installed users — Claude Code sees the same version string and keeps the cached copy. Always bump + tag.

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/plugin install` can't find the plugin | The marketplace `source` is resolved relative to the **marketplace root** (the dir containing `.claude-plugin/`), not relative to `marketplace.json`. Since the plugin IS the repo root, this repo uses `source: "./"`. Re-run `claude plugin validate .`. |
| Teammates not auto-prompted | `.claude/settings.json` must be committed and the folder trusted; check `extraKnownMarketplaces` repo/owner and that `enabledPlugins` uses `plugin@marketplace`. |
| "A skill said it would block but didn't" | Skills can't block by design. The block is couche-0 infra — run `scripts/bootstrap-smoke-test.sh` and confirm `terraform apply` ran. |
| Generator refused | It read `org-profile.yaml` and your stack doesn't match. Fix the profile or pick the right generator. |
| MCP server errors on start | Missing env (`AZURE_SUBSCRIPTION_ID` / `LANGFUSE_*`). Set it, or ignore — the server just won't connect. |
| LSP does nothing | `pyright` not installed: `pip install pyright`. |
| Update didn't take | You pushed commits without bumping `plugin.json` `version` + tagging. See §7. |

---

## Arming the PR gate (branch-protection) — dogfooded on this repo

The local hooks (pre-commit + the in-session `.claude` guards) give fast feedback, but the
**only** thing that truly blocks a non-conforming merge is GitHub **branch-protection**. It is
available only when the repo is **public** or on **GitHub Pro/Team** (a private free-tier repo
returns `403` — branch-protection simply can't be set). Fenrir arms it on its own `main`:

**Required status checks** (the job `name:` / status contexts in `.github/workflows/`):
`dashboard (lint + type + test)`, `lint + type + test hooks`, `validate manifests`, `delivery-trace`.

**Option A — IaC (reproducible):** `branch-protection.tf` at the repo root.
```bash
terraform init
terraform apply -var="repository=Fenrir"   # needs a GitHub token with repo admin (GITHUB_TOKEN)
```

**Option B — one-shot `gh api`:**
```bash
gh api -X PUT repos/<owner>/Fenrir/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": { "strict": true,
    "contexts": ["dashboard (lint + type + test)", "lint + type + test hooks", "validate manifests", "delivery-trace"] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0, "dismiss_stale_reviews": true },
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "restrictions": null
}
JSON
```
Solo maintainer → `required_approving_review_count: 0` (you can't self-approve); a team raises it
to ≥1 and turns on code-owner reviews (add a root `CODEOWNERS`). Verify with
`python3 scripts/techlead_report.py --root .` → "branch-protection: ARMED".

> `delivery-trace` makes every PR reference a User Story on the dashboard board — drop it from
> the contexts (and the `.tf`) if you don't run the companion board.

---

Design rationale and the 6 red-team iterations: see `DELIVERY-SKILLSET.md` and `CHANGELOG.md`. Solo end-to-end walkthrough: `GETTING-STARTED.md`. Repo layout: `README.md`.
