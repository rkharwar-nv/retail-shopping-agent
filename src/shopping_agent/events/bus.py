"""M-EVENTS: EventBus facade.

Callers interact with ONLY this class — not the sink directly.
Makes it trivial to swap the Phase 1 JSONL sink for Kafka later.
"""

from __future__ import annotations

from typing import Any, Protocol

from shopping_agent.config import EventsConfig
from shopping_agent.events.schema import Event
from shopping_agent.events.sinks.jsonl import JsonlFileSink


class Sink(Protocol):
    def write(self, event: Event) -> None: ...


class _NullSink:
    def write(self, event: Event) -> None:  # noqa: ARG002
        pass


class _StdoutSink:
    def write(self, event: Event) -> None:
        print("[event]", event.model_dump_json(exclude_none=True))


class EventBus:
    """Single entry point for all event emission. Non-blocking by spec."""

    def __init__(self, sink: Sink) -> None:
        self._sink = sink

    def publish(
        self,
        event_type: str,
        *,
        session_id: str,
        turn_id: str,
        trace_id: str,
        **attrs: Any,
    ) -> None:
        """Publish an event. attrs are folded into either the envelope's
        typed fields (role, provider, model_id, duration_ms) or stored
        under `.attrs`."""
        typed_fields = {"role", "provider", "model_id", "duration_ms"}
        typed = {k: attrs.pop(k) for k in list(attrs) if k in typed_fields}
        event = Event(
            event_type=event_type,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            attrs=attrs,
            **typed,
        )
        self._sink.write(event)


def build_bus(cfg: EventsConfig) -> EventBus:
    """Factory: wire up the right sink per config."""
    if cfg.sink == "jsonl_file":
        return EventBus(JsonlFileSink(cfg.path))
    if cfg.sink == "stdout":
        return EventBus(_StdoutSink())
    if cfg.sink == "null":
        return EventBus(_NullSink())
    raise ValueError(f"Unknown events sink: {cfg.sink}")
