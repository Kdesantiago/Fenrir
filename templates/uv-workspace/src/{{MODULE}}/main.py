"""FastAPI application entrypoint. Run from this dir: `uv run uvicorn main:app --reload`."""

from fastapi import FastAPI

from api.routes import router
from core.settings import settings

app = FastAPI(title=settings.app_name)
app.include_router(router)
