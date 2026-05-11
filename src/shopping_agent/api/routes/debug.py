"""Debug routes — developer introspection.

Gated by config.debug.enabled. If disabled, routes return 404 to avoid
leaking the existence of the endpoint in production.

SECURITY REMINDER: traces contain raw prompts and raw model responses.
Do NOT enable debug in a shared or prod environment.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from shopping_agent.api.dependencies import get_trace_buffer_dep
from shopping_agent.debug.trace import DebugTraceBuffer

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/trace/{session_id}")
def get_trace(
    session_id: str,
    buf: DebugTraceBuffer = Depends(get_trace_buffer_dep),
):
    """Return recent upstream-call traces for a session.

    Returns 404 if debug is disabled — presence of this endpoint
    is itself information we don't want to leak in prod."""
    if not buf.enabled:
        raise HTTPException(status_code=404, detail="debug disabled")
    entries = buf.get(session_id)
    return {"session_id": session_id, "count": len(entries), "entries": entries}


@router.delete("/trace/{session_id}")
def clear_trace(
    session_id: str,
    buf: DebugTraceBuffer = Depends(get_trace_buffer_dep),
):
    if not buf.enabled:
        raise HTTPException(status_code=404, detail="debug disabled")
    buf.clear(session_id)
    return {"cleared": session_id}
