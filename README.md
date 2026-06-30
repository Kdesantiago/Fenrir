# 🐺 Fenrir

> **The wolf that guards your delivery.** A Claude Code plugin that turns "ship some code" into a standardized, gated, repeatable lifecycle — the same way, in every repo.

Fenrir gives Claude Code a coordinated **pack** of 47 skills, 14 subagents, 7 commands, and 16 hooks (safety + delivery-tracking). You go from a raw idea to a reviewed, gated pull request — with the boring-but-critical parts (security, tests, docs, CI, branch protection, releases) done consistently instead of "however we felt like it this time."

---

## Why

Most teams re-invent delivery in every repo: different CI, different review bar, secrets leaking into commits, docs going stale, no real gate before merge. Fenrir makes one **golden path** portable across all your repos, and — crucially — backs it with **real enforcement**, not just good intentions.

> **The one idea:** *skills advise, infra enforces.* A skill is text the AI can skip. So the actual gate is deterministic infrastructure — git hooks + CI required-checks + branch-protection — which Fenrir installs for you. Advice gives fast feedback; infra blocks bad merges.

---

## Install

In any Claude Code session (CLI or app):

```text
/plugin marketplace add Kdesantiago/Fenrir@v1.7.0
/plugin install fenrir@fenrir-marketplace
```

> Pin to the latest release tag (check the repo's **Releases**). Private repo → you need access to it for the install to resolve.

**Team-wide auto-install:** commit a `.claude/settings.json` (see `templates/team-settings.json`) so teammates are auto-prompted to install when they open the repo — no manual step.

---

## Quick start

1. **Start a repo:**
   - **Brand-new project** → `/fenrir:init <project-name> [services…]` — scaffolds a clean **uv-workspace monorepo** (one `uv.lock` at the root, services as members under `src/`) and then installs the gate.
   - **Existing repo** → ask "bootstrap this repo to the Fenrir standard".

   The gate (couche 0) = pre-commit hooks, in-session safety hooks, the CI required-checks workflow, branch-protection-as-code, and an `org-profile.yaml`.

2. **Bootstrap + arm the gate** (one cross-OS command, no terraform/gh needed):
   ```bash
   python scripts/bootstrap.py          # detects Python, bakes the abs interpreter into the
                                        # enforcement hooks, merges settings.json (de-duped),
                                        # copies hooks, and runs the smoke test — idempotent, all OSes
   python scripts/set_branch_protection.py --repo OWNER/REPO   # arm branch-protection (the real merge block)
   ```
   `set_branch_protection.py` is pure stdlib: it PUTs the rule via the GitHub REST API when `GITHUB_TOKEN` + a repo slug are present, else prints the exact Settings → Branches web-UI steps + REST payload (no terraform, no `gh`). The smoke test is now `python scripts/bootstrap_smoke_test.py` (Windows/macOS/Linux), superseding the old `.sh`.

3. **Declare your stack** in `org-profile.yaml` (platform, framework, auth, observability, LLM provider…). Generators read it and refuse to emit wrong-stack code.

4. **Work, the standardized way:**
   - `/fenrir:challenge-me <idea>` — turns a fuzzy idea into a scoped, red-teamed spec, then drives the build.
   - `/fenrir:deliver <task>` — orchestrates architect → coder → tests → review → gates → PR.
   - `/fenrir:ship` — runs the automated pre-PR review and opens the PR.
   - Or ask for any single capability by intent ("design the API for X", "add a safe migration", "set up canary on AKS", "cut a release"…).

New here? Read **[GETTING-STARTED.md](GETTING-STARTED.md)** — a 10-minute, end-to-end walkthrough.

---

## What's inside

| Layer | Examples |
|---|---|
| **Scaffold & gate** | `repo-bootstrap`, `delivery-gates`, `security-review`, `quality-master`, `deps`, `secrets`, `image-scan` |
| **Build (stack-aware)** | `api-first`, `iac-gen`, `auth-gen`, `observability-gen`, `frontend-gen`, `cronjob`, `db-migration`, `data-model`, `caching`, `event-driven`, `knowledge-base`, `realtime-transport` |
| **Author & evolve code** | `refactor`, `simplify` (DRY/KISS), `optimize` (under one constraint), `explain` (didactic), `report` (session digest), `tech-debt` (catalog debt + drift → board) |
| **Ship to production** | `progressive-delivery` (canary/blue-green on AKS), `gitops` (Flux/Argo CD), `feature-flags`, `load-test`, `release` |
| **Operate** | `incident-runbook`, `alert-delivery`, `error-budget`, `llm-cost-monitor`, `online-llm-eval`, `us-cost-tracking` (per-US cost on the dashboard), `workflow-efficiency` (cheap-but-good multi-agent runs) |
| **Azure live-ops** (via `az` MCP, read-only/advisory) | `azure-audit`, `azure-cost`, `azure-waf`, `azure-monitor-ops` |
| **LLM apps** | `llm-gen`, `retriever` (RAG), `langgraph-workflow`, `ai-threat-model` (design-time LLM threat modeling) |
| **Agents** | `architect`, `coder`, `context-engineering`, `qa-tester`, `reviewer`, `red-team-destroyer`, `doc-keeper`, `stack-adapter`, `security-guardrail`, `delivery-tracker`, `azure-architect`, `azure-sre`, `azure-deploy-verifier`, `dat-architect` |
| **Commands** | `/fenrir:init` (new uv-workspace repo + gate), `/fenrir:challenge-me`, `/fenrir:plan` (plan-first: board breakdown before code), `/fenrir:deliver`, `/fenrir:ship`, `/fenrir:auto` (autonomous plan→deliver→ship; stops at the human merge gate), `/fenrir:status` (tech-lead report) |
| **Safety hooks** | block secret-exfil & gate-bypass, scan prompts/web for injection, keep docs in sync, audit config changes |
| **Delivery-tracking hooks** | attribute each commit's real cost to the US it delivers (`tracking-attribute`, on every `git commit`), make tracing a commit obligatory (`tracking-guard`), ledger subagent runs + backstop the session tail (`tracking-collect`/`tracking-finalize`) — so **every US carries its real per-US cost automatically**; plus **subject-focused compaction** (`precompact-focus` snapshots the active-US dev subject before a compaction; `session-context` re-injects it after, so the summary serves the work in progress), an **auto-retrospective** written to `docs/delivery-memory/retros/` when an epic closes, and a **branch→plan nudge** (`branch-plan-check` reminds you to `/fenrir:plan` when you create a feature branch with no board plan); driven by the `delivery-tracker` agent |

Stack-aware generators target **Azure / AKS / Azure DevOps** first (and GitHub), Python (uv / FastAPI / Streamlit), and LLM/RAG apps — but read your declared profile and refuse on mismatch rather than guessing.

---

## Local-first by default

Fenrir installs and runs with **zero cloud CLIs** — no `az`, `terraform`, `gh`, or `kubectl` needed to bootstrap a repo, arm the gate, or ship a PR. The plugin ships an **empty `.mcp.json`**, so the cloud MCP servers (`azure`, `langfuse`) do **not** auto-start.

To enable the **optional** Azure / observability layer: copy the desired server block(s) from `.mcp.json.example` into `.mcp.json`, set the env vars (`AZURE_SUBSCRIPTION_ID` for azure; `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` [/ `LANGFUSE_HOST`] for langfuse), and restart Claude Code. `gh` / `az` / `terraform` are optional accelerators, and the Azure / IaC / cloud skills are an opt-in layer (plugin keyword `local-first`).

---

## Requirements

- **Claude Code** (CLI or app) — to install and use the plugin.
- Per consuming repo, when you run the gate: `git`, `python3` (≥3.9), and `pre-commit`. That's it — `python scripts/bootstrap.py` wires everything and `python scripts/set_branch_protection.py` arms branch-protection with just a `GITHUB_TOKEN` (or the printed web-UI steps). **No `terraform`, no `gh`/`az` required.**
- Optional bundled extras activate only when you opt in: Azure/Langfuse **MCP** servers (copy into `.mcp.json` + set env vars), a Python **LSP** (`pip install pyright`), and AKS deploy-watch **monitors**.

---

## Companion: monitoring dashboard

A local web app under **[dashboard/](dashboard/README.md)** — real token/cost/agent telemetry parsed from `~/.claude` + an **agent-driven Agile board** (Epic → Feature → User Story → Task) with a kanban, charts, and a CLI the agents use to manage the board. A **Reference** tab self-documents the whole pack — every agent/hook/skill/command + description, searchable — and the Agents view auto-refreshes so you can watch subagents execute live. Plus **cost accounting**: per-US (per-agent) token/USD cost, a cost trace you can **filter by epic/feature/US** (newest-first by default, sort-by-cost optional), and **subagent attribution** (which named subagent ran, when, how much — reconciled, no double-count). Companion app, not a plugin component. `cd dashboard && uv sync --extra dev && uv run uvicorn backend.app:app`.

## Docs

- **[GETTING-STARTED.md](GETTING-STARTED.md)** — solo, end-to-end (10 min).
- **[CHANGELOG.md](CHANGELOG.md)** — what changed, per release.
- **[DELIVERY-SKILLSET.md](DELIVERY-SKILLSET.md)** — design rationale & architecture.
- **[dashboard/README.md](dashboard/README.md)** — the monitoring dashboard (telemetry + Agile board).
- Maintainers publishing/updating the plugin itself: **[PUBLISHING.md](PUBLISHING.md)**.

## License

MIT.
