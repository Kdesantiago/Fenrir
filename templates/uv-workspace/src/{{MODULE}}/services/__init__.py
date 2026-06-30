"""services — business logic. Pure functions / service classes the api/ layer calls."""

from schemas import HealthResponse


def health_status() -> HealthResponse:
    """Minimal liveness payload — replace with the real service logic."""
    return HealthResponse(status="ok", service="{{MODULE}}")
