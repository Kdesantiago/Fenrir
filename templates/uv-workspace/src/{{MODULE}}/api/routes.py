"""HTTP routes. The router is mounted in main.py via app.include_router(router)."""

from fastapi import APIRouter

from schemas import HealthResponse
from services import health_status

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — delegates to the services/ layer."""
    return health_status()
