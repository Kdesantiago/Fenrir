# 0005 — /fenrir:init module layout: flat, self-contained per-module projects (ChatBot_IC)

- Status: Accepted (supersedes the earlier **Candidate A** decision recorded in this same ADR)
- Date: 2026-06-29
- Deciders: architect agent (Python packaging), per direct user direction (ChatBot_IC reference)
- Profile: framework=fastapi (`templates/org-profile.yaml:5`). Module runtime floor Python **3.9**.

## Status note — what changed and why

An earlier revision of this ADR adopted **Candidate A**: a uv-workspace monorepo where each
module was a workspace *member* `src/<module>/` containing a same-named importable package dir
`src/<module>/<module>/{core,services,api,schemas}`, so imports were namespaced
(`import <module>.core.settings`) and the whole repo shared one root `uv.lock` and one venv via
`uv sync --all-packages`.

**That decision is SUPERSEDED.** The user provided the **ChatBot_IC** reference layout as the
authority and was explicit: each module is a **self-contained project** — `src/<module>/` FLAT
(`core/ services/ api/ schemas/ …` directly inside it), **one `pyproject.toml` and one `.env`
per module**, **its own `.venv`**, **no uv-workspace**, **no shared root lock**, and **no
`src/<module>/<module>` nest**. Imports are **module-local top-level**:
`from core.settings import settings`, `from services import health_status`,
`from api.routes import router`.

The reason Candidate A's central objection (namespacing, to avoid a global `core`/`services`/`api`
collision) **no longer applies** is the load-bearing change below.

## Decision

**Adopt the ChatBot_IC flat, self-contained per-module model.** Each declared module is an
independent project rooted at `src/<module>/`:

```
<project>/                 # repo ROOT
  pyproject.toml           #   DEV TOOLING ONLY ([tool.ruff],[tool.mypy] strict,[tool.pytest],[tool.coverage]); NOT a package, NOT a workspace
  .python-version  .gitignore  README.md  docs/.gitkeep
  src/<module>/            # SELF-CONTAINED project: its own pyproject, .venv, lockfile, .env
    pyproject.toml         #   [project] name="<module>", requires-python ">=3.9", deps: fastapi/pydantic-settings/uvicorn; hatchling wheel target
    .env.example           #   documented env vars (<MODULE>_ prefix) -> copy to .env
    README.md
    __init__.py            #   __version__
    main.py                #   FastAPI app, include_router(api.routes.router)
    core/{__init__,settings,config}.py   # settings.py = pydantic-settings BaseSettings, env_prefix="<MODULE>_", reads .env
    api/{__init__,routes}.py             # APIRouter, GET /health -> services
    services/__init__.py                 # health_status() business stub
    schemas/__init__.py                  # a pydantic model (HealthResponse)
    tests/test_smoke.py                  # from core.settings import settings; from services import health_status
```

The module dir `src/<module>/` is BOTH the project root and the import root. There is exactly
**one** level (`src/` → the module dir); the old empty `src/<module>/<module>` double-nest is gone.

### Why FLAT is now correct (the collision Candidate A feared cannot occur)

Candidate A rejected the flat layout (its "Candidate B-flat") on one ground: a flat wheel ships
top-level `core/`, `services/`, `api/`, so **two modules sharing one venv** both register a global
`core` in `sys.modules` and **collide**. That objection is conditional on *one shared venv* — which
is precisely the uv-workspace assumption this ADR drops.

Under the ChatBot_IC model **each module has its OWN `.venv` and its OWN lockfile** (`cd
src/<module> && uv sync`). A module's `core`/`services`/`api`/`schemas` are top-level packages
**only inside that module's own interpreter**. Two modules are never imported into the same
`sys.modules`, so there is **no cross-module `import core` collision** — the very problem
namespacing existed to solve is dissolved by isolation rather than by a package prefix. The
benefits of namespacing (which cost the empty nest) are no longer needed:

- **Isolation > namespacing.** Independent venvs also isolate *dependency versions* per module
  (module A on fastapi 0.115, module B on 0.138) — a property a single shared workspace lock cannot
  give. This matches how ChatBot_IC ships each service as a standalone deployable.
- **Simpler imports.** `from core.settings import settings` (no `<module>.` prefix) is what the
  reference uses and what generators downstream target. The module name appears once, in
  `[project].name` and the env prefix — not threaded through every import.
- **No meaningless directory.** The user's original complaint ("don't ship a pointless
  `src/app/app`") is honored literally: the flat layout has zero redundant nest.

### Wheel target (validated, not asserted)

Because the layout is flat, the module's wheel must ship several top-level packages **plus** two
single-file top-level modules. The validated `pyproject.toml` target is:

```toml
[tool.hatch.build.targets.wheel]
packages = ["core", "api", "services", "schemas"]
force-include = { "main.py" = "main.py", "__init__.py" = "__init__.py" }
```

`packages = [...]` ships the four flat package dirs; `force-include` ships `main.py` and the
top-level `__init__.py` (which are modules, not packages, so `packages` alone would omit them).
This list is **load-bearing**: drop a name and `uv build` produces a wheel missing that package
with **no error**. The build was run and the wheel contents inspected (below) to prove it ships a
real package tree, not a `dist-info`-only empty wheel.

## Empirical evidence (uv 0.9.15, hatchling, rendered with module=`app`)

The template was rendered into a scratch copy (`{{MODULE}}`→`app`, `{{MODULE_ENV}}`→`APP`),
`cd src/app`, and the full loop run. Observed results:

| Check | Command | Result |
|---|---|---|
| resolve + install (own venv) | `uv sync` | OK — `src/app/.venv` created, fastapi/pydantic-settings/uvicorn + dev tools installed |
| module-local imports | `uv run python -c "import core.settings, services, api.routes, main"` | OK — all resolve; `core.settings.settings.app_name == "app"` |
| env prefix | `APP_APP_NAME=probe APP_DEBUG=true uv run python -c …` | OK — settings read `APP_*` (`app_name=probe`, `debug=True`) |
| **wheel is non-empty** | `uv build` then inspect `dist/app-0.1.0-*.whl` | OK — ships `core/{__init__,config,settings}.py`, `api/{__init__,routes}.py`, `services/__init__.py`, `schemas/__init__.py`, `main.py`, `__init__.py` (NOT dist-info-only) |
| tests | `uv run pytest` | **3 passed** (settings load, service stub, `GET /health` via TestClient) |
| lint | `uv run ruff check .` | **All checks passed** |
| types | `uv run mypy .` | **Success: no issues found in 10 source files** |

Two adjustments were required for a green gate under the flat layout and are baked into the root
`pyproject.toml`:

- **ruff isort `known-first-party = ["core","api","services","schemas","main"]`** — without it,
  ruff's import sorter classifies the module-local packages as third-party and flags I001 on
  every file. These package names are stable across all modules (the ChatBot_IC convention), so the
  list is fixed.
- **mypy `explicit_package_bases = true` + `namespace_packages = true`**, and
  `python_version = "3.10"** — the module's own top-level `__init__.py` otherwise makes mypy see
  each file twice (`app.schemas` and `schemas`); `explicit_package_bases` resolves it when mypy runs
  from inside the module dir. mypy ≥ 2.x refuses `python_version = "3.9"` (must be ≥ 3.10), so the
  mypy *type-check* target is `3.10` (a safe superset) while the *runtime* floor stays
  `requires-python ">=3.9"` and ruff stays `target-version = "py39"`.

## Consequences

- (+) `/fenrir:init` emits the ChatBot_IC layout the user asked for: flat `src/<module>/{core,api,
  services,schemas}`, module-local `from core.settings import settings`, one project per module.
- (+) Per-module isolation: own venv, own lockfile, own `.env`, own dependency set. No cross-module
  `import core` collision (each module is its own interpreter), and version drift between modules is
  allowed by construction.
- (+) Zero redundant nesting — the old empty `src/<module>/<module>` is gone.
- (-) **No single root `uv.lock` and no root venv.** The dev loop and CI are now **per module**
  (`cd src/<module> && uv sync && uv run pytest`). Repo-level tooling that assumed root-level
  `uv sync --all-packages` + `pytest --cov=src` (the `repo-bootstrap` CI workflow and
  `delivery-gates`) must iterate the module dirs instead. This ADR does not edit those skills;
  the per-module note is carried to `init.md` step 3 and flagged as an open issue.
- (-) The root `pyproject.toml` carries lint/type/test config but is **not** an installable package
  and **not** a uv workspace — anything that read `[project]`/`[tool.uv.workspace]` from it must stop.
- Commits the project to: any future module generator (api-first, llm-gen, etc.) targets the FLAT
  `src/<module>/{api,services,core,schemas}` with module-local top-level imports — **not** a
  `<module>.`-prefixed namespace.

## Reference

- **ChatBot_IC** (user-provided reference implementation): `src/<module>/` flat with `core/`,
  `services/`, `api/ (routers)`, `schemas/`; one `pyproject.toml` and one `.env` per module; each
  module a self-contained project with its own `.venv`; no uv-workspace shared lock; imports are
  module-local top-level (`from core.settings import settings`). This ADR adopts that model verbatim
  for `/fenrir:init`.

## Implementation notes for downstream

- **template:** `templates/uv-workspace/` restructured to the flat model — dev-tooling-only root
  `pyproject.toml` (ruff `known-first-party`, mypy `explicit_package_bases`/strict, pytest,
  coverage), and one example module `src/{{MODULE}}/` with `pyproject.toml`, `.env.example`,
  `README.md`, `__init__.py`, `main.py`, `core/{__init__,settings,config}.py`,
  `api/{__init__,routes}.py`, `services/__init__.py`, `schemas/__init__.py`, `tests/test_smoke.py`.
  Placeholders: `{{PROJECT_NAME}}`, `{{MODULE}}`, `{{MODULE_ENV}}`.
- **init.md:** step 2 rewritten to capture `<module>` ONCE and derive the module dir, `[project].name`,
  the fixed wheel `packages` list, the `<MODULE>_` env prefix, and the module-local smoke import. The
  old "rename ALL FOUR aligned names" / double-nest wording is deleted. Dev loop documented as
  `cd src/<module> && uv sync && cp .env.example .env`.
- **OPEN — repo-bootstrap / delivery-gates:** their CI/test stages assume root-level tooling
  (`uv sync --all-packages`, `pytest --cov=src`, one root `uv.lock`). They need a per-module note
  (iterate `src/<module>/` dirs). Not edited here; tracked as an open issue + doc-delta.
