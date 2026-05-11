"""Health endpoints: cheap liveness + config-verified readiness."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from shopping_agent.api.dependencies import get_config

router = APIRouter(tags=["health"])


@router.get("/healthz")
def liveness() -> dict[str, str]:
    """Process is up. No dependency checks."""
    return {"status": "ok"}


@router.get("/readyz")
def readiness() -> dict[str, str]:
    """Config loaded + secrets resolved. Does NOT call any model."""
    try:
        cfg = get_config()
        return {
            "status": "ready",
            "schema_version": str(cfg.schema_version),
            "role1_model": cfg.models.role1.model_id,
            "events_sink": cfg.events.sink,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"not ready: {e}") from e
