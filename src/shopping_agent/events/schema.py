"""M-EVENTS: event schema.

Versioned, non-PII event envelope. Every event carries session_id,
turn_id, trace_id so analytics can correlate without joining on text.

This is a minimal Phase-1 schema. A richer taxonomy (PRD §12) will
land in Lesson 2's M-EVENTS spec; keeping this lean until then.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid4().hex


class Event(BaseModel):
    """Canonical Phase-1 event envelope."""

    schema_version: int = 1
    event_id: str = Field(default_factory=_new_id)
    event_type: str                       # e.g. "model.call.started"
    occurred_at: str = Field(default_factory=_now_iso)

    session_id: str
    turn_id: str
    trace_id: str

    # Optional correlators
    role: int | None = None               # 1, 2, or 3 (for model.* events)
    provider: str | None = None
    model_id: str | None = None
    duration_ms: int | None = None

    # Free-form structured extras — MUST NOT contain raw PII,
    # prompt text, response text, or auth credentials.
    attrs: dict[str, Any] = Field(default_factory=dict)


# ─── Named event types (Phase 1) ─────────────────────────────
# Keeping these as string constants (not an enum) so other modules
# can add types without modifying a central enum.

EV_SESSION_START = "session.start"
EV_SESSION_END = "session.end"
EV_TURN_RECEIVED = "turn.received"
EV_TURN_COMPLETED = "turn.completed"
EV_MODEL_CALL_STARTED = "model.call.started"
EV_MODEL_CALL_SUCCEEDED = "model.call.succeeded"
EV_MODEL_CALL_FAILED = "model.call.failed"
EV_ENVELOPE_PRODUCED = "envelope.produced"
EV_ERROR = "error"
