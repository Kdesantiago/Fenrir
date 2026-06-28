# Getting Started — fenrir (solo, 10 min)

This is everything you need to use the plugin **alone**, end to end. No external context required.

> Mental model in one line: **skills advise, infra enforces.** A skill is text the agent may skip; the gate is `pre-commit` + an in-session hook + CI required-checks + branch-protection. `repo-bootstrap` installs that gate; everything else rides on top.

---

## 0. Prerequisites

| Tool | Why | Required |
|---|---|---|
| `git` | repo + hooks | yes |
| `python3` | the in-session guard hook (stdlib only) | yes |
| `pre-commit` | local lint/type/secret gate | yes (`pipx install pre-commit`) |
| `terraform` | applies branch-protection (the real merge block) | for enforcement |
| `gh` or `az` CLI | opens PRs (`/fenrir:ship`) | for PR flow |
| `pipx` | runs `semgrep` / `cyclonedx-bom` in CI | CI only |

---

## 1. Install the plugin

```bash
# A. via marketplace (recommended — pinned, one source of truth)
/plugin marketplace add <git-url-of-this-repo>
/plugin install fenrir@fenrir-marketplace

# B. local dev (symlink)
ln -s "$(pwd)" ~/.claude/plugins/fenrir
```

Never copy individual files into per-repo `~/.claude` — that drifts. Consume the pinned plugin.

---

## 2. Bootstrap a repo (installs the gate)

In the target repo, ask Claude Code:

> "bootstrap this repo to the delivery standard"

`repo-bootstrap` then, idempotently:

1. Writes/confirms `org-profile.yaml` (declares your stack — see step 3).
2. Installs **pre-commit** hooks (all three types): `pre-commit install && pre-commit install --hook-type pre-push && pre-commit install --hook-type commit-msg`.
3. Installs the **in-session guard**: copies `hooks/delivery-guard.py` → `.claude/hooks/` and merges `.claude/settings.json`. Now an agent can't `git --no-verify`, force-push to `main`, or quietly edit gate files from inside a session.
4. Drops the **CI required-checks** workflow — GitHub (`required-checks.yml`) or Azure (`azure-pipelines.yml`) by your provider.
5. Drops **branch-protection-as-code** — `branch-protection.tf` (GitHub) or `azure-branch-policy.tf` (Azure). **`terraform apply` this — it is the only thing that truly blocks a non-conforming merge.**
6. Repo hygiene: `.gitignore`, `renovate.json`, `CODEOWNERS`, conventional-commits.

Then prove the gate is wired:

```bash
bash scripts/bootstrap-smoke-test.sh
```

It checks: all 3 hook types installed, `pre-commit run --all-files` clean, CI job names == branch-protection required checks, terraform valid. Non-zero exit = a hole.

---

## 3. Declare your stack — `org-profile.yaml`

Generators **refuse on mismatch** rather than emit wrong-stack code. Edit the file `repo-bootstrap` created:

```yaml
platform: aks            # aks | webapp | k8s | serverless | vm | ecs
framework: fastapi       # fastapi | express | spring | streamlit | none
auth_provider: entra     # entra | okta | keycloak | auth0 | none
obs_backend: grafana     # grafana | datadog | cloudwatch | honeycomb | langfuse
llm_provider: anthropic  # anthropic | openai | azure | bedrock | vertex | none
front: streamlit         # react | vue | svelte | streamlit | html | none
template_version: "1.0.0"
```

---

## 4. Daily use

### Plan first (the work starts on the board)
> "/fenrir:plan — add endpoint X" → decomposes it into one **Feature** + **atomic User Stories** on the board (one thing each), creates the `feat/<feature>` branch — **no code yet**. Development then proceeds one US at a time. `/fenrir:deliver` and `/fenrir:challenge-me` check for this plan and create it if missing, so you can also jump straight to deliver. **One Feature = one branch = one PR**; the PR delivers that Feature's US (the `delivery-trace` check enforces a US reference).

### Orchestrated delivery (the common path)
> "/fenrir:deliver — add endpoint X" → ensures a board plan exists (creates it if not), then routes **light** (hotfix: coder → gates → ship) or **full** (feature: architect → coder → qa-tester → review → gates → ship) by a deterministic git diff measure, building the US one at a time (cost lands per-US). Writes a spec artifact to `docs/specs/` that every subagent reads. Stops before PR on any hard failure.

> "/fenrir:ship" → opens a conventional-commit PR, links the ADR + spec, runs gates for local feedback, surfaces CI status. It does **not** claim to enforce — branch-protection does.

### Skills (trigger by asking)
| Want | Say |
|---|---|
| Init the gate | "bootstrap this repo" → `repo-bootstrap` |
| Fast local check | "run delivery gates on my diff" → `delivery-gates` |
| SAST/SBOM/threat | "security review this diff" → `security-review` |
| IaC / auth / obs / front / LLM scaffold | "generate the Helm chart" etc → the matching `*-gen` (reads `org-profile.yaml`; iac-gen does aks/webapp/k8s) |
| Docs | "regenerate the README/changelog" → `doc-generator` |
| Record a decision / waive a gate / log drift | "remember this decision", "waive check X until Y" → `memory-keeper` (in-repo delivery-memory) |

### Subagents (delegated personas)
`architect` (design + ADR), `coder` (implements the change against the spec/ADR — the builder in the delivery flow), `context-engineering` (what fills the LLM context window + versioned prompt artifacts), `qa-tester` (write new tests + repros), `reviewer` (PR-hygiene verdict), `red-team-destroyer` (ruthless adversarial review — "red-team this"), `stack-adapter` (translates standard cloud ops into your enterprise Azure wrappers, reading `stack-interface.yaml`), `doc-keeper` (keeps CHANGELOG/READMEs/API-docs in sync with the diff), `security-guardrail` (opt-in LLM guardrail that judges prompts for injection/safety), `delivery-tracker` (traces a session's work onto the Agile board — Epic→Feature→US→Task — and attributes its real cost). Running the coder as a subagent means its token spend is attributable to the US (see the dashboard's cost accounting).

---

## 5. The enforcement model (why this actually standardizes)

```
            advises (skippable)        enforces (deterministic)
            ───────────────────        ────────────────────────
local       delivery-gates skill   →   pre-commit hooks (commit/push)
                                       + in-session .claude hooks (agent guard + security:
                                         deny --no-verify/secret-exfil/zero-access, injection scans)
                                       + delivery-tracking hooks (auto-trace work to a US +
                                         attribute cost; tracking-guard gates git commit)
merge       reviewer subagent      →   CI required-checks (incl. delivery-trace)
            /fenrir:ship pre-PR review        + branch-protection-as-code  ← the real block
```

Security layer (ported from PAI, pure Python): `prompt-guard` (input), `delivery-guard` (tool calls), `content-scanner` (fetched content), `config-audit` (settings changes), `session-context` (injects the live contract). All log to `.claude/audit/security-events.jsonl`.

If you only adopt one thing: run `repo-bootstrap` and `terraform apply` the branch-protection. That alone makes delivery non-optional.

---

## 6. FAQ

- **"A skill said it would block but didn't."** Skills can't block — by design. The block is infra (steps 2–5). Re-check the smoke test.
- **"Generator refused."** It read `org-profile.yaml` and your stack doesn't match. Fix the profile or pick the right generator.
- **"I'm on Azure, not GitHub."** Use `azure-pipelines.yml` + `azure-branch-policy.tf`. Never ship the GitHub variant onto Azure.
- **"The in-session guard is annoying."** It only `ask`s on gate-file edits and force-push-to-main, and `deny`s `--no-verify`. That's the point — it's the agent guardrail.
