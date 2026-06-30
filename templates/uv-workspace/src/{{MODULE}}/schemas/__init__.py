"""schemas — pydantic request/response models shared by api/ and services/."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    service: str
