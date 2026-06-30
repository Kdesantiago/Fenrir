# {{MODULE}}

A self-contained module (its own project, venv, lockfile, and `.env`).

## Layout (flat — this dir is the import root)
```
pyproject.toml     # [project] name={{MODULE}}; runtime deps; hatchling wheel target
.env.example       # documented env vars ({{MODULE_ENV}}_ prefix); copy to .env
__init__.py        # __version__
main.py            # FastAPI app (include api.routes.router)
core/              # settings.py (pydantic-settings) + config.py constants
api/               # routes.py — APIRouter, GET /health
services/          # business logic (health_status())
schemas/           # pydantic models
tests/             # module-local tests
```

Imports are module-local top-level: `from core.settings import settings`,
`from services import health_status`, `from api.routes import router`.

## Dev loop
```bash
uv sync                  # install this module + dev tools into ./.venv
cp .env.example .env     # local config (reads {{MODULE_ENV}}_ env vars)
uv run pytest
uv run ruff check .
uv run uvicorn main:app --reload
```
