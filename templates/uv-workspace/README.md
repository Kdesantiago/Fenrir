# {{PROJECT_NAME}}

A repo of **self-contained modules**. There is **no uv workspace** and **no shared lockfile**:
each module under `src/<module>/` is its own project — its own `pyproject.toml`, its own `.venv`,
its own lockfile, its own `.env`. The repo root carries shared dev tooling (ruff/mypy/pytest)
only; it is not a package. (Modeled on the ChatBot_IC reference layout — see `docs/adr/0005`.)

## Layout
```
pyproject.toml            # repo root: DEV TOOLING ONLY (ruff/mypy/pytest config); NOT a package
.python-version  .gitignore  docs/
src/<module>/             # one self-contained project = one shippable module
  pyproject.toml          #   [project] name=<module>, its runtime deps + hatchling build config
  .env.example            #   documented env vars (<MODULE>_ prefix); copy to .env
  README.md               #   module-local readme
  __init__.py             #   __version__
  main.py                 #   FastAPI app: include_router(api.routes.router)
  core/                   #   settings (pydantic-settings) + config constants
  api/                    #   APIRouter (HTTP layer)
  services/               #   business logic
  schemas/                #   pydantic models
  tests/                  #   module-local tests
```

Imports inside a module are **module-local top-level** (the module dir is the import root):
`from core.settings import settings`, `from services import health_status`,
`from api.routes import router`. Because each module installs into its OWN venv, there is no
cross-module `import core` collision — two modules never share a `sys.modules`.

## Develop a module
```bash
cd src/<module>
uv sync                 # resolve + install THIS module (and dev tools) into src/<module>/.venv
cp .env.example .env    # local config
uv run pytest           # this module's tests
uv run ruff check .     # lint
uv run uvicorn main:app --reload   # run the app
```

> Run each module from **inside** `src/<module>/`. The module dir is the project root and the
> import root; there is no `uv sync --all-packages` and no root venv to share.

## Add a module
Copy an existing `src/<module>/` → `src/<new>/`, then update `[project].name`, the
`[tool.hatch.build.targets.wheel].packages` list, the `.env.example` prefix, and the smoke
import. (`/fenrir:init` does this for you from the module name.)

> Bootstrapped by `/fenrir:init`; the delivery gate (pre-commit + CI + branch-protection) is
> installed by `repo-bootstrap`.
