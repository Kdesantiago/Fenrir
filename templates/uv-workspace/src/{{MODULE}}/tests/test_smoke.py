"""Smoke tests — run from src/{{MODULE}}/ (`uv run pytest`); imports are module-local top-level."""

from core.settings import settings
from services import health_status


def test_settings_loads() -> None:
    assert settings.app_name


def test_health_ok() -> None:
    assert health_status().status == "ok"


def test_health_endpoint() -> None:
    from fastapi.testclient import TestClient

    from main import app

    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
