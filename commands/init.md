---
description: Scaffold a clean uv-workspace monorepo from scratch AND put the delivery gate in place — the front door for a brand-NEW repo. Creates the root uv workspace (one uv.lock, services as members under src/<service>), each service's package + tests, then runs repo-bootstrap to install couche-0 (hooks + CI + branch-protection). Usage: /fenrir:init <project-name> [service ...]. NOT for an existing project (use repo-bootstrap to add the gate to one).
---

# /fenrir:init <project-name> [service ...]

The single front door for a brand-new repo: **clean structure + the gate, in one command.** Users go through this — they do NOT call `repo-bootstrap` directly. (`repo-bootstrap` is the lower-level skill for adding the gate to an *existing* repo; `/fenrir:init` orchestrates it for a new one.)

## 0. Preconditions
- The target dir must be **empty / new**. If a `pyproject.toml` or `src/` already exists, STOP — this is not a new repo; route to `repo-bootstrap` to add the gate without re-scaffolding.
- `uv` must be available: `command -v uv` (else `pipx install uv`, or stop with that instruction).

## 1. Gather (one short round)
- **project name** (kebab) and the **service list** (one or more; default a single `app`). Python is the Fenrir baseline **3.12** (the template + CI + semgrep all pin it; don't offer an arbitrary version — it won't propagate). Also capture **framework** (fastapi/streamlit/…) so the gate step doesn't re-ask.

## 2. Scaffold the uv workspace (from `templates/uv-workspace/`)
Copy the whole `templates/uv-workspace/` tree (it ships `.gitignore`, `docs/`, root `pyproject.toml`, `.python-version`, and one example member), then adapt:
- **Root `pyproject.toml`** — a *virtual* coordinator (`[tool.uv] package = false`) with `[tool.uv.workspace] members = ["src/*"]`, shared dev tooling in `[dependency-groups] dev`, and `[tool.ruff]`/`[tool.mypy]`/`[tool.pytest.ini_options]`/`[tool.coverage]`. Rename `workspace-root` → `<project-name>`.
- **Per service** — copy `src/example_service` → `src/<service>` for each declared service, and rename ALL FOUR aligned names or imports break:
  1. the **member dir** `src/<service>`,
  2. the **package dir** `src/<service>/<package>/`,
  3. `[project].name` in that member's `pyproject.toml`,
  4. `[tool.hatch.build.targets.wheel].packages` in that member's `pyproject.toml`.
  (A single-service repo keeps the one member — the workspace shape stays; it just has one member.)
- **Substitute `{{PROJECT_NAME}}`** in `README.md`.
- **Lock + sync ONCE at the root:** `uv lock` → a single root `uv.lock` (commit it); `uv sync --all-packages --dev` → one venv with every member installed editable (must be `--all-packages`: the virtual root doesn't depend on the members).

## 3. Put the gate in place (invoke `repo-bootstrap`)
**Hand off, don't re-ask:** write a partial `org-profile.yaml` now from the answers (framework, the service list, `template_version`), then run the `repo-bootstrap` skill — it consumes/confirms that profile (rather than re-interrogating you) and installs pre-commit + the in-session hooks + CI required-checks + branch-protection-as-code + delivery-memory + `scripts/bootstrap-smoke-test.sh`. The CI runs at the **repo root** over the whole workspace (`uv sync --all-packages` + `pytest --cov=src`) — no per-service matrix to keep in sync. Then:
```bash
terraform apply                         # arm branch-protection (the real gate)
bash scripts/bootstrap-smoke-test.sh    # prove the gate is wired
```

## 4. (optional) Raise the bar
Run `quality-master` for the strict mypy/ruff + Hypothesis tier if you want expert-grade from day one (the workspace already ships strict defaults).

## 5. Verify
- `uv lock --check` clean, `uv run pytest` green on the smoke tests, smoke-test passes.

## Refuses when
- The target already contains a project (`pyproject.toml` / `src/`) → don't re-init; use `repo-bootstrap`.
- `uv` is unavailable and the user won't install it.

## Output
- The created tree + the single root `uv.lock`, the chosen services, `org-profile.yaml`, and the gate status (armed / smoke-test result).
