# 🐺 Fenrir

> **The wolf that guards your delivery.** A Claude Code plugin that turns "ship some code" into a standardized, gated, repeatable lifecycle — the same way, in every repo.

Fenrir gives Claude Code a coordinated **pack** of 47 skills, 14 subagents, 6 commands, and 15 hooks (safety + delivery-tracking). You go from a raw idea to a reviewed, gated pull request — with the boring-but-critical parts (security, tests, docs, CI, branch protection, releases) done consistently instead of "however we felt like it this time."

---

## Why

Most teams re-invent delivery in every repo: different CI, different review bar, secrets leaking into commits, docs going stale, no real gate before merge. Fenrir makes one **golden path** portable across all your repos, and — crucially — backs it with **real enforcement**, not just good intentions.

> **The one idea:** *skills advise, infra enforces.* A skill is text the AI can skip. So the actual gate is deterministic infrastructure — git hooks + CI required-checks + branch-protection — which Fenrir installs for you. Advice gives fast feedback; infra blocks bad merges.

---

## Install

In any Claude Code session (CLI or app):

```text
/plugin marketplace add Kdesantiago/Fenrir@v1.6.0
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

2. **Arm the gate** (the part that actually blocks bad merges):
   ```bash
   terraform apply                      # branch-protection
   bash scripts/bootstrap-smoke-test.sh # prove the gate is wired
   ```

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
| **Commands** | `/fenrir:init` (new uv-workspace repo + gate), `/fenrir:challenge-me`, `/fenrir:plan` (plan-first: board breakdown before code), `/fenrir:deliver`, `/fenrir:ship`, `/fenrir:status` (tech-lead report) |
| **Safety hooks** | block secret-exfil & gate-bypass, scan prompts/web for injection, keep docs in sync, audit config changes |
| **Delivery-tracking hooks** | attribute each commit's real cost to the US it delivers (`tracking-attribute`, on every `git commit`), make tracing a commit obligatory (`tracking-guard`), ledger subagent runs + backstop the session tail (`tracking-collect`/`tracking-finalize`) — so **every US carries its real per-US cost automatically**; plus **subject-focused compaction** (`precompact-focus` snapshots the active-US dev subject before a compaction; `session-context` re-injects it after, so the summary serves the work in progress) and an **auto-retrospective** written to `docs/delivery-memory/retros/` when an epic closes; driven by the `delivery-tracker` agent |

Stack-aware generators target **Azure / AKS / Azure DevOps** first (and GitHub), Python (uv / FastAPI / Streamlit), and LLM/RAG apps — but read your declared profile and refuse on mismatch rather than guessing.

---

## Requirements

- **Claude Code** (CLI or app) — to install and use the plugin.
- Per consuming repo, when you run the gate: `git`, `python3`, `pre-commit`, and (to arm branch-protection) `terraform`, plus `gh` or `az`.
- Optional bundled extras activate when present: Azure/Langfuse **MCP** servers (need their env vars), a Python **LSP** (`pip install pyright`), and AKS deploy-watch **monitors**.

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
