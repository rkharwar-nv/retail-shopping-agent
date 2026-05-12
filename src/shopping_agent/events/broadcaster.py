"""In-process event fan-out.

Wraps an EventBus sink so every published event also gets delivered
to in-memory subscribers: the SSE streaming endpoint, and the
session-stats aggregator used by the /ui activity panel.

Non-invasive. Existing code continues to call `bus.publish(...)` as
before. The broadcaster is the SINK wrapper, not a new interface.

Thread-safety note: FastAPI runs sync routes in a threadpool, so
subscribers must tolerate being appended-to from any thread. We use
a simple Lock around the subscriber list.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from shopping_agent.events.schema import Event


class BroadcastSink:
    """Wraps another Sink; fans out to subscribers + the underlying sink."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self._subs: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        # Keep last N events per session for replay + stats.
        # deque cap is per session.
        self._replay: dict[str, deque[Event]] = {}
        self._replay_cap = 200

    def write(self, event: Event) -> None:
        # Forward to underlying sink first (never block on subscribers).
        self._inner.write(event)
        # Store per-session replay buffer.
        with self._lock:
            buf = self._replay.setdefault(event.session_id,
                                          deque(maxlen=self._replay_cap))
            buf.append(event)
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(event)
            except Exception:  # pragma: no cover — subscribers must not crash us
                pass

    # ───── public API for subscribers ─────

    def subscribe(self, cb: Callable[[Event], None]) -> Callable[[], None]:
        """Register a callback. Returns an unsubscribe function."""
        with self._lock:
            self._subs.append(cb)

        def _off() -> None:
            with self._lock:
                try:
                    self._subs.remove(cb)
                except ValueError:
                    pass

        return _off

    def history(self, session_id: str) -> list[Event]:
        """All buffered events for a session, oldest first."""
        with self._lock:
            buf = self._replay.get(session_id)
            return list(buf) if buf else []


def aggregate_stats(events: list[Event]) -> dict[str, Any]:
    """Collapse a list of events into the activity-panel shape.

    Counts calls + tokens per model, calls per role, and builds a
    simple timeline. Ignores events that don't carry the fields we
    need — schema is additive.
    """
    from datetime import datetime

    calls_by_model: dict[str, dict[str, Any]] = {}
    calls_by_role: dict[str, int] = {}
    agents_active: set[str] = set()
    timeline: list[dict[str, Any]] = []
    turns: set[str] = set()

    start_ms: dict[str, int] = {}  # turn_id -> epoch ms of first event

    for e in events:
        turns.add(e.turn_id)
        # occurred_at is ISO string; parse once per event.
        try:
            ts_ms = int(datetime.fromisoformat(e.occurred_at).timestamp() * 1000)
        except Exception:
            ts_ms = 0
        start_ms.setdefault(e.turn_id, ts_ms)
        t_rel = ts_ms - start_ms[e.turn_id]

        model_id = e.model_id or "(unknown)"
        role_str = f"role{e.role}" if e.role is not None else "(unknown)"
        usage = (e.attrs or {}).get("usage") or {}

        if e.event_type == "model.call.succeeded":
            bucket = calls_by_model.setdefault(model_id, {
                "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "reasoning_tokens": 0, "total_latency_ms": 0,
                "role": role_str,
            })
            bucket["calls"] += 1
            bucket["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            bucket["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            bucket["reasoning_tokens"] += int(usage.get("reasoning_tokens") or 0)
            bucket["total_latency_ms"] += int(e.duration_ms or 0)
            calls_by_role[role_str] = calls_by_role.get(role_str, 0) + 1
            agents_active.add(role_str)
            timeline.append({
                "t_ms": t_rel, "turn_id": e.turn_id,
                "event": f"{role_str}.done",
                "duration_ms": e.duration_ms,
                "model_id": model_id,
            })
        elif e.event_type == "model.call.started":
            agents_active.add(role_str)
            timeline.append({
                "t_ms": t_rel, "turn_id": e.turn_id,
                "event": f"{role_str}.start",
                "model_id": model_id,
            })
        elif e.event_type == "turn.received":
            timeline.append({"t_ms": t_rel, "turn_id": e.turn_id,
                             "event": "turn.received"})
        elif e.event_type == "turn.completed":
            timeline.append({"t_ms": t_rel, "turn_id": e.turn_id,
                             "event": "turn.completed"})
        elif e.event_type == "model.call.failed":
            timeline.append({"t_ms": t_rel, "turn_id": e.turn_id,
                             "event": f"{role_str}.error",
                             "error": (e.attrs or {}).get("error")})

    return {
        "turns": len(turns),
        "calls_by_model": calls_by_model,
        "calls_by_role": calls_by_role,
        "agents_active": sorted(agents_active),
        "sub_agents": [],  # populated as specialists come online
        "timeline": timeline,
    }
