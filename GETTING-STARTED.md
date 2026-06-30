# Getting Started — fenrir (solo, 10 min)

This is everything you need to use the plugin **alone**, end to end. No external context required.

> Mental model in one line: **skills advise, infra enforces.** A skill is text the agent may skip; the gate is `pre-commit` + an in-session hook + CI required-checks + branch-protection. `repo-bootstrap` installs that gate; everything else rides on top.

---

## 0. Prerequisites

| Tool | Why | Required |
|---|---|---|
| `git` | repo + hooks + push (the only tool a PR needs) | yes |
| `python3` (≥3.9) | bootstrap + the in-session guard hook (stdlib only) | yes |
| `pre-commit` | local lint/type/secret gate | yes (`pipx install pre-commit`) |
| `GITHUB_TOKEN` | arms branch-protection via REST (or use the printed web-UI steps) | for enforcement |
| `gh` or `az` CLI | optional PR accelerator — not required (`git push` + the Compare URL is the default) | optional |
| `terraform` | optional — the pure-Python `set_branch_protection.py` replaces it | optional |
| `pipx` | runs `semgrep` / `cyclonedx-bom` in CI | CI only |

> **Local-first:** the one cross-platform entrypoint is `python scripts/bootstrap.py` (Windows/macOS/Linux). The whole golden path — bootstrap, arm the gate, ship a PR — works with **zero** `az` / `terraform` / `gh` / `kubectl`. The Azure/IaC/cloud skills are an optional layer (plugin keyword `local-first`).

---

## 1. Install the plugin

```bash
# A. via marketplace (recommended — pinned, one source of truth)
/plugin marketplace add <git-url-of-this-repo>
/plugin install fenrir@fenrir-marketplace

# B. local dev (test uncommitted changes — cross-platform, no symlink)
claude --plugin-dir /absolute/path/to/fenrir   # then /reload-plugins after edits
```

Never copy individual files into per-repo `~/.claude` — that drifts. Consume the pinned plugin.

> **Windows note:** use Git for Windows and the `py` launcher (`python --version` ≥ 3.9). The `bash` blocks in this guide assume a POSIX shell; the one cross-platform entrypoint that works the same on every OS is `python scripts/bootstrap.py`.

---

## 2. Bootstrap a repo (installs the gate)

Run the one-command bootstrap (cross-OS, idempotent), then ask Claude Code to fill the stack-aware pieces:

```bash
python scripts/bootstrap.py [REPO_ROOT]   # defaults to the current repo
```

It detects a working Python (≥3.9), **bakes that interpreter's absolute path** into the enforcement hooks (so they run on this machine without a PATH `python`), JSON-merges `.claude/settings.json` **per event without clobbering your own hooks** (de-duped, so a re-run is a no-op), copies the enforcement hooks, runs the migrate de-dupe, and finishes with the smoke test. This replaces the old manual "hand-merge `templates/.claude/settings.json`" step.

Then ask Claude Code "bootstrap this repo to the delivery standard" so `repo-bootstrap` writes the stack-aware artifacts, idempotently:

1. Writes/confirms `org-profile.yaml` (declares your stack — see step 3).
2. Installs **pre-commit** hooks (all three types): `pre-commit install && pre-commit install --hook-type pre-push && pre-commit install --hook-type commit-msg`.
3. Confirms the **in-session guard** wired by `bootstrap.py` (an agent can't `git --no-verify`, force-push to `main`, or quietly edit gate files from inside a session).
4. Drops the **CI required-checks** workflow — GitHub (`required-checks.yml`) or Azure (`azure-pipelines.yml`) by your provider.
5. Drops **branch-protection-as-code** and arms it. The pure-Python path needs no terraform/gh:
   ```bash
   python scripts/set_branch_protection.py --repo OWNER/REPO [--check NAME ...]
   ```
   It PUTs the rule via the GitHub REST API when `GITHUB_TOKEN` is set, else prints the exact Settings → Branches web-UI steps + the equivalent REST payload. **Arming this is the only thing that truly blocks a non-conforming merge.**
6. Repo hygiene: `.gitignore`, `renovate.json`, `CODEOWNERS`, conventional-commits.

`bootstrap.py` already runs the smoke test; re-run it any time to prove the gate is wired:

```bash
python scripts/bootstrap_smoke_test.py
```

It checks (cross-platform): all 3 hook types installed, `pre-commit run --all-files` clean, CI job names == branch-protection required checks, enforcement hooks wired into `.claude/settings.json`. Non-zero exit = a hole. (Supersedes the old `bootstrap-smoke-test.sh`.)

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
> "/fenrir:deliver — add endpoint X" → ensures a board plan exists (creates it if not), then builds the US one at a time (cost lands per-US). **`light` is the default route** — an inline edit or one specialist subagent (→ gates → ship) — keeping token cost low. The **full** multi-agent pipeline (architect → coder → qa-tester → review → gates → ship) is **opt-in via `--full`**, or auto-triggered only for **risky/large diffs** (auth / iac / migrations / security path hits, or over the file/LOC size threshold). Either route writes a spec artifact to `docs/specs/` that every subagent reads, and **both** end with the mandatory qa-tester + red-team validation gate. Stops before PR on any hard failure.

> "/fenrir:ship" → opens a conventional-commit PR, links the ADR + spec, runs gates for local feedback, surfaces CI status. It does **not** claim to enforce — branch-protection does.

**Shipping a PR needs only `git`.** The No-CLI path is the default: `git push -u origin <branch>`, then open the Compare & pull-request URL derived from `git remote get-url origin`:
- GitHub: `…/compare/<default>...<branch>?expand=1`
- Azure DevOps: `…/pullrequestcreate?sourceRef=<branch>&targetRef=<default>`

CI status is viewable in the browser PR checks panel; branch-protection is armed via the platform REST API with a token (`python scripts/set_branch_protection.py` — no terraform, no `gh`/`az`). `gh`/`az` are optional accelerators, not requirements.

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
`architect` (design + ADR), `coder` (implements the change against the spec/ADR — the builder in the delivery flow), `context-engineering` (what fills the LLM context window + versioned prompt artifacts), `qa-tester` (write new tests + repros), `reviewer` (PR-hygiene verdict), `red-team-destroyer` (ruthless adversarial review — "red-team this"), `stack-adapter` (translates standard cloud ops into your enterprise Azure wrappers, reading `stack-interface.yaml`), `doc-keeper` (keeps CHANGELOG/READMEs/API-docs in sync with the diff), `security-guardrail` (opt-in LLM guardrail that judges prompts for injection/safety), `delivery-tracker` (traces a session's work onto the Agile board and attributes its real cost), the Azure live-ops agents (`azure-architect`/`azure-sre`/`azure-deploy-verifier`), and `dat-architect` (writes/audits a DAT — the full technical architecture doc). Running the coder as a subagent means its token spend is attributable to the US (see the dashboard's cost accounting).

### Context-window hygiene (compaction + delegation)
Long sessions fill the context window. Two mechanisms keep that manageable:
- **Auto-compaction is Claude Code's, not Fenrir's.** Claude Code compacts automatically as you approach the context-window limit (on by default in recent versions); there is **no Fenrir setting** for a numeric "250–300K" threshold — that knob, if any, lives in Claude Code's own config, and `/compact` triggers it manually anytime. Fenrir's `precompact-focus` hook (PreCompact) **focuses** that compaction onto your active US + dev subject (snapshots `.claude/tracking/compact-focus.md`, re-injected on the next `SessionStart` with `source=compact`) so the summary serves the work in progress, not a flat recap. Hooks are **snapshotted at session start**, so a freshly-installed hook engages from the **next** session — verify it's wired in the dashboard **Reference** tab (it lists every hook + when it fires).
- **Delegate to keep the main context lean.** `/fenrir:plan`/`deliver`/`challenge-me` run substantive work (decompose, design, build, validate) as **subagents** — their tool churn stays in *their* context, not yours. This is the bigger lever: it stops the main window filling in the first place, so compaction matters less.

---

## 5. The enforcement model (why this actually standardizes)

```
            advises (skippable)        enforces (deterministic)
            ───────────────────        ────────────────────────
local       delivery-gates skill   →   pre-commit hooks (commit/push)
                                       + in-session .claude hooks (agent guard + security:
                                         deny --no-verify/secret-exfil/zero-access, injection scans)
                                       + delivery-tracking hooks (auto-trace work to a US +
                                         attribute each commit's cost to its US; tracking-guard
                                         gates git commit, tracking-attribute charges it)
merge       reviewer subagent      →   CI required-checks (incl. delivery-trace)
            /fenrir:ship pre-PR review        + branch-protection-as-code  ← the real block
```

Security layer (ported from PAI, pure Python): `prompt-guard` (input), `delivery-guard` (tool calls), `content-scanner` (fetched content), `config-audit` (settings changes), `session-context` (injects the live contract). All log to `.claude/audit/security-events.jsonl`.

If you only adopt one thing: run `python scripts/bootstrap.py` and `python scripts/set_branch_protection.py` to arm branch-protection. That alone makes delivery non-optional — no terraform, no `gh`/`az`.

---

## 6. FAQ

- **"A skill said it would block but didn't."** Skills can't block — by design. The block is infra (steps 2–5). Re-check the smoke test.
- **"Generator refused."** It read `org-profile.yaml` and your stack doesn't match. Fix the profile or pick the right generator.
- **"I'm on Azure, not GitHub."** Use `azure-pipelines.yml` + `azure-branch-policy.tf`. Never ship the GitHub variant onto Azure.
- **"The in-session guard is annoying."** It only `ask`s on gate-file edits and force-push-to-main, and `deny`s `--no-verify`. That's the point — it's the agent guardrail.
- **"Context compaction didn't fire / isn't subject-focused."** Two separate things: (1) **WHEN** compaction happens is Claude Code's own **auto-compact threshold** (a client setting, on by default in recent versions as you approach the context-window limit) — Fenrir cannot *trigger* it from a hook. (2) The `precompact-focus` hook only **focuses** that compaction onto your active US + dev subject *when it fires*, by snapshotting `compact-focus.md` (re-injected on the next `SessionStart` with `source=compact`). Hooks are **snapshotted at session start**, so a freshly-installed hook engages from the **next session** — if you don't see the focus, start a new session. To compact sooner, lower Claude Code's auto-compact threshold in its settings (not a Fenrir setting); `/compact` triggers it manually any time.
- **"Do commands need the `fenrir:` prefix?"** Yes — always invoke as `/fenrir:plan`, `/fenrir:deliver`, etc. (the plugin namespace). All docs use that form.
