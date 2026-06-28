---
name: repo-bootstrap
description: Use when adding the org delivery standard (couche-0 gate) to an EXISTING repository — installs the enforcement infra that actually gates delivery. Generates pre-commit/pre-push hooks, CI required-checks workflow, branch-protection-as-code, org-profile.yaml, .gitignore, renovate, CODEOWNERS, conventional-commits config. Idempotent: skips files that already exist. For a brand-NEW repo from scratch, prefer the `/fenrir:init` command (it scaffolds the uv-workspace structure THEN runs this). NOT for running checks on an existing diff (use delivery-gates), NOT for app feature code.
---

# Repo Bootstrap — Couche 0 (the real gate)

This skill installs the **deterministic enforcement infrastructure**. A skill cannot block anything; these generated artifacts can, because git hooks, CI required-checks, and branch protection run outside the model's discretion.

## When to use
- An **existing** repo missing the org standard ("bootstrap this repo", "add the gate", "set up the delivery standard").
- Invoked **by `/fenrir:init`** as the gate step after it scaffolds a new uv-workspace.

## When NOT to use
- A brand-new repo from scratch → use the `/fenrir:init` command (it builds the structure first, then calls this). Don't scaffold structure here.
- Running lint/test on a diff → `delivery-gates`.
- The repo already has all couche-0 files → report and stop (idempotent).

## Steps

1. **Detect stack** → write/confirm `org-profile.yaml` (see `templates/org-profile.yaml`). Ask the user for any key you cannot infer (platform, framework, auth_provider, obs_backend, llm_provider, front). This profile drives every generator downstream.
2. **Install hooks** — copy `templates/.pre-commit-config.yaml`; run all three install types: `pre-commit install && pre-commit install --hook-type pre-push && pre-commit install --hook-type commit-msg`. The `commit-msg` install is required or conventional-commit linting silently no-ops. Local gate: lint (ruff), type (mypy), format, secret-scan (gitleaks), commit-msg. **Secret-scan lives here and ONLY here.**
3. **In-session guard + security layer (couche 0, agent-side)** — copy ALL of `hooks/*.py` → `.claude/hooks/`, copy `scripts/track_session.py` → `.claude/scripts/` (the delivery-tracking engine the hooks call), and MERGE `templates/.claude/settings.json` into the repo's `.claude/settings.json` (don't clobber existing hooks — append per event). Wires the pure-Python hooks: `delivery-guard` (PreToolUse — deny `--no-verify`/secret-exfil/zero-access paths, ask on force-push/gate-file edits), `prompt-guard` (UserPromptSubmit — injection scan), `content-scanner` (PostToolUse web — injection-in-content warning), `config-audit` (PostToolUse — audits `.claude/settings.json` changes), `session-context` (SessionStart — injects the active delivery contract + open gate-exceptions), plus the **delivery-tracking** trio: `tracking-guard` (PreToolUse Bash — makes tracing a `git commit` obligatory: auto-creates a US, or denies in strict mode), `tracking-collect` (SubagentStop — ledgers each subagent run for precise cost attribution), `tracking-finalize` (SessionEnd — auto-attributes the session's real cost to its US). In-session twin of the pre-commit/CI gate; no bun/node/daemon. **Tracking needs the `dashboard/` companion app present**; without it the tracking hooks fail-open (no-op). Env knobs: `FENRIR_TRACK_ENFORCE=strict` (block untraced commits), `FENRIR_TRACK_DISABLE=1` (off).
   - **delivery-memory**: create `docs/delivery-memory/` scaffold (decisions/, `gate-exceptions.jsonl`, `drift-log.jsonl`, `lessons.md`) — managed by the `memory-keeper` skill; the `session-context` hook reads it.
   - **stack-interface (optional)**: if the org wraps Azure (internal CLI/backends), copy `templates/stack-interface.yaml` → **repo root** (`./stack-interface.yaml` — the `session-context` hook and `stack-adapter` agent both read it from root) and fill it; generators then emit wrapper commands, not raw `az`. Skip the file if standard CLIs are used.
4. **CI required-checks** — pick the workflow by the repo's CI provider: GitHub → `templates/ci/required-checks.yml`; Azure DevOps → `templates/ci/azure-pipelines.yml`. Runs `test` (incl. coverage gate) + `sast` + `build` as **required status checks** = the merge gate. **Do not ship GitHub Actions onto an Azure repo** (and vice-versa). Before writing: 
   - **Preserve an existing pipeline.** If the repo already has `azure-pipeline*.yml` or `.github/workflows/*.yml`, do NOT overwrite — diff, report, and offer to merge required jobs in. Adding a second weaker pipeline is a regression.
   - **Detect uv.** If services ship `uv.lock`, the template's uv branch (`uv sync --all-extras --dev`, `uv run pytest`) is used; pin Python to the services' `requires-python` (e.g. 3.12, not 3.13).
   - **Copy `templates/.semgrep.yml` → repo root.** The `sast` check hard-runs `semgrep --config .semgrep.yml`; without this file SAST is red forever.
   - Set PR triggers to the repo's real branches (e.g. `dev`, `main`, `release/*`), not main-only.
5. **Branch-protection-as-code** — GitHub → `templates/branch-protection.tf`; Azure DevOps → `templates/azure-branch-policy.tf`. Fill repo/branch; `terraform apply` (this is the only thing that truly blocks a non-conforming merge). The required-check names MUST equal the CI job/stage names — verify the coupling.
6. **Repo hygiene** — `.gitignore` (skip if present, e.g. when `/fenrir:init` already wrote one); copy `templates/renovate.json` → `renovate.json` (patch/minor auto-merge after green CI, major manual) and `templates/CODEOWNERS` → `CODEOWNERS` (fill the `@your-org/*` placeholders + risk-path owners); conventional-commits; `README.md` skeleton (skip if present). Also copy `scripts/bootstrap-smoke-test.sh` into the repo so the gate can be verified locally.
7. **Version assertion** — stamp the consumed plugin/template version in `org-profile.yaml` (`template_version:`) so `delivery-gates` can fail loud on mismatch.

## Idempotency
For every file: if it exists, diff against the template and report drift; never clobber without the user confirming.

## Output / validation
- Run `pre-commit run --all-files` once to prove hooks work.
- Print a checklist: which couche-0 artifacts were created vs already present vs drifted.
- Remind the user: the gate is live only after `terraform apply` on branch-protection.

## Refuses when
- No write access / not a git repo → stop, explain.
- Stack cannot be determined and the user won't declare the profile → stop (generators downstream would emit wrong-stack code).
