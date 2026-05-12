"""Session stats + SSE event stream (dev-gated).

Both endpoints require config.debug.enabled to avoid leaking in prod.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from shopping_agent.api.dependencies import get_config, get_event_bus
from shopping_agent.config import AppConfig
from shopping_agent.events.broadcaster import BroadcastSink, aggregate_stats
from shopping_agent.events.bus import EventBus

router = APIRouter()


def _require_debug(cfg: AppConfig) -> None:
    if not cfg.debug.enabled:
        raise HTTPException(status_code=404, detail="Not found")


def _broadcaster(bus: EventBus) -> BroadcastSink:
    bc = bus.broadcaster
    if bc is None:
        raise HTTPException(status_code=503,
                            detail="event broadcaster unavailable")
    return bc


@router.get("/sessions/{session_id}/stats")
def session_stats(
    session_id: str,
    cfg: AppConfig = Depends(get_config),
    bus: EventBus = Depends(get_event_bus),
) -> dict[str, Any]:
    """Aggregated counters for the activity panel."""
    _require_debug(cfg)
    bc = _broadcaster(bus)
    events = bc.history(session_id)
    stats = aggregate_stats(events)
    stats["session_id"] = session_id
    return stats


@router.get("/events/stream/{session_id}")
async def events_stream(
    session_id: str,
    request: Request,
    cfg: AppConfig = Depends(get_config),
    bus: EventBus = Depends(get_event_bus),
) -> StreamingResponse:
    """Server-Sent Events stream, scoped to one session."""
    _require_debug(cfg)
    bc = _broadcaster(bus)

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    loop = asyncio.get_running_loop()

    def _cb(event) -> None:
        if event.session_id != session_id:
            return
        # Cross-thread enqueue: BroadcastSink.write may run in the
        # threadpool where sync routes execute.
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:  # pragma: no cover — loop shutting down
            pass

    unsub = bc.subscribe(_cb)

    # Replay existing history so the panel hydrates immediately.
    for existing in bc.history(session_id):
        try:
            queue.put_nowait(existing)
        except asyncio.QueueFull:
            break

    async def _iter():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Heartbeat comment keeps proxies from killing the conn.
                    yield ": keepalive\n\n"
                    continue
                payload = event.model_dump(mode="json", exclude_none=True)
                yield f"event: {event.event_type}\n"
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            unsub()

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(_iter(), media_type="text/event-stream",
                             headers=headers)
