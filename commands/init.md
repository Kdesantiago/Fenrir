---
description: Scaffold a clean repo of self-contained modules from scratch AND put the delivery gate in place — the front door for a brand-NEW repo. Each module under src/<module>/ is its own project (own pyproject, own .venv, own lockfile, own .env); the repo root carries shared dev tooling only. Then runs repo-bootstrap to install couche-0 (hooks + CI + branch-protection). Usage: /fenrir:init <project-name> [module ...]. NOT for an existing project (use repo-bootstrap to add the gate to one).
---

# /fenrir:init <project-name> [module ...]

The single front door for a brand-new repo: **clean structure + the gate, in one command.** Users go through this — they do NOT call `repo-bootstrap` directly. (`repo-bootstrap` is the lower-level skill for adding the gate to an *existing* repo; `/fenrir:init` orchestrates it for a new one.)

The scaffold is a repo of **self-contained modules** (the ChatBot_IC flat layout, see `docs/adr/0005-init-module-layout.md`): **no uv workspace, no shared lockfile**. Each module under `src/<module>/` is an independent project with its own `pyproject.toml`, its own `.venv`, its own lockfile, and its own `.env`. The repo root `pyproject.toml` is dev tooling only.

## 0. Preconditions
- The target dir must be **empty / new**. If a `pyproject.toml` or `src/` already exists, STOP — this is not a new repo; route to `repo-bootstrap` to add the gate without re-scaffolding.
- `uv` must be available: `command -v uv` (else `pipx install uv`, or stop with that instruction).

## 1. Gather (one short round)
- **project name** (kebab) and the **module list** (one or more; default a single `app`). The module runtime floor is **Python 3.9** (`requires-python = ">=3.9"`, matching the ChatBot_IC reference); ruff targets `py39` and mypy type-checks against 3.10 semantics (the lowest mypy supports, a safe superset for 3.9 code). Also capture **framework** (fastapi/streamlit/…) so the gate step doesn't re-ask.

## 2. Scaffold the flat per-module tree (from `templates/uv-workspace/`)
Copy the whole `templates/uv-workspace/` tree (it ships `.gitignore`, `docs/`, `.python-version`, the dev-tooling-only root `pyproject.toml`, and ONE example module dir `src/{{MODULE}}/`), then adapt. The template uses three placeholders — `{{PROJECT_NAME}}`, `{{MODULE}}`, `{{MODULE_ENV}}` — and **everything is derived from the module name captured ONCE per module.** There is no "rename four aligned names" and no `src/<module>/<module>` double-nest: the module dir `src/<module>/` is itself the import root, and packages inside it are flat (`core/ api/ services/ schemas/`).

- **Root `pyproject.toml`** — dev tooling only (`[tool.ruff]` with `known-first-party = ["core","api","services","schemas","main"]`, `[tool.mypy]` strict + `explicit_package_bases`, `[tool.pytest.ini_options]`, `[tool.coverage]`). It is **not a package and not a uv workspace** — no `[project]`, no `[tool.uv.workspace]`. Substitute `{{PROJECT_NAME}}` → `<project-name>` (it appears only in a comment + README).

- **Per module** — the example module dir is literally named `src/{{MODULE}}/`. For each declared module, **capture the module name `<module>` ONCE** (a snake_case Python identifier, e.g. `app`, default `app`), copy `src/{{MODULE}}/` → `src/<module>/`, and derive every token from `<module>`:

  | Token | Value (derived from `<module>`) | Where it lands |
  |---|---|---|
  | module dir | `src/<module>/` | the project root **and** the import root (no inner package dir) |
  | `{{MODULE}}` | `<module>` | `[project].name`, the `__init__.py`/`README` docstrings, `app_name` default, `service=` in `services/` |
  | `{{MODULE_ENV}}` | `<module>`.upper() (e.g. `app` → `APP`) | `env_prefix` in `core/settings.py`, the `<MODULE>_` vars in `.env.example` |
  | wheel packages | `[tool.hatch.build.targets.wheel] packages = ["core","api","services","schemas"]` + `force-include` of `main.py`/`__init__.py` | the module's `pyproject.toml` — **fixed, NOT renamed** (the flat package names are stable across every module) |
  | `.env.example` prefix | `<MODULE>_` (= `{{MODULE_ENV}}_`) | each documented var |
  | smoke import | `from core.settings import settings`; `from services import health_status` | `tests/test_smoke.py` — module-local top-level (no `<module>.` prefix) |

  Substitute `{{MODULE}}`/`{{MODULE_ENV}}` in every copied file (including renaming the dir itself). A single-module repo keeps exactly one `src/<module>/`.

- **Per-module lock + sync — NOT at the root.** Each module is self-contained, so resolve and install **inside each module dir** (this is also the dev loop documented in its README):
  ```bash
  cd src/<module>
  uv sync                 # resolve -> src/<module>/uv.lock (commit it); install into src/<module>/.venv
  cp .env.example .env    # local config
  ```
  Repeat per module. There is **no** `uv lock`/`uv sync --all-packages` at the root and **no** root `uv.lock` — modules do not share a venv or a lockfile, so two modules' flat `core/` packages never collide in one `sys.modules`.

## 3. Put the gate in place (invoke `repo-bootstrap`)
**Hand off, don't re-ask:** write a partial `org-profile.yaml` now from the answers (framework, the module list, `template_version`), then run the `repo-bootstrap` skill — it consumes/confirms that profile (rather than re-interrogating you) and installs pre-commit + the in-session hooks + CI required-checks + branch-protection-as-code + delivery-memory. **CI note (flat per-module):** because there is no root venv or root `uv.lock`, the CI/test step must run **per module** — for each `src/<module>/`, `cd src/<module> && uv sync && uv run pytest` (the `templates/ci/required-checks.yml` per-module variant; coverage per-module). A single root `uv sync --all-packages` / `pytest --cov=src` no longer applies; if `repo-bootstrap`'s default workflow assumes the old root-tooling shape, adjust the test stage to iterate the module dirs. Then arm + verify the gate — **cloud-optional, cross-OS, no `terraform`/`gh` required:**
```bash
python scripts/bootstrap.py                                  # arm the in-session gate (cross-OS):
                                                             #   detect interpreter, bake it into the hooks,
                                                             #   merge .claude/settings.json, copy hooks, verify
python scripts/set_branch_protection.py --repo OWNER/REPO    # arm branch-protection (the only true merge gate):
                                                             #   REST via GITHUB_TOKEN when set, else prints the
                                                             #   Settings → Branches web-UI steps (no gh/terraform)
python scripts/bootstrap_smoke_test.py                       # prove the gate is wired (cross-platform)
```
`terraform`/`gh` remain only as optional accelerators if you already run them — they are no longer on the canonical arm/verify path.

## 4. (optional) Raise the bar
Run `quality-master` for the strict mypy/ruff + Hypothesis tier if you want expert-grade from day one (the root `pyproject.toml` already ships strict ruff + mypy defaults that every module inherits).

## 5. Verify
- For each module: `cd src/<module>`, `uv lock --check` clean, `uv run pytest` green on the smoke tests, `uv run ruff check .` clean. Then the bootstrap smoke-test passes.

## Refuses when
- The target already contains a project (`pyproject.toml` / `src/`) → don't re-init; use `repo-bootstrap`.
- `uv` is unavailable and the user won't install it.

## Output
- The created tree (one self-contained project per `src/<module>/`, each with its own `uv.lock`), the chosen modules, `org-profile.yaml`, and the gate status (armed / smoke-test result).
