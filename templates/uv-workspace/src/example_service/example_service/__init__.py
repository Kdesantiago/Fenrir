"""example_service — a workspace member package. Rename to your service."""

__version__ = "0.1.0"


def health() -> dict[str, str]:
    """Minimal liveness payload — replace with the real service entrypoint."""
    return {"status": "ok", "service": "example-service"}
