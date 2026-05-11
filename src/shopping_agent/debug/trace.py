"""In-memory upstream-call trace buffer.

When `config.debug.enabled` is true, Role N adapters record the full
upstream call (assembled prompts, raw request kwargs, raw response
text, token usage, timings) into a process-local ring buffer keyed
by session_id. The /debug/trace/<session_id> route reads from here.

SECURITY:
- Data lives in RAM only, never persisted.
- Evicted after ttl_seconds or when buffer_size is exceeded.
- The route that exposes this must be gated by config.debug.enabled.
- Contains raw prompts and raw responses — DO NOT ship with debug on.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class DebugTraceBuffer:
    """Thread-safe per-session ring buffer of upstream call traces."""

    def __init__(self, enabled: bool, buffer_size: int, ttl_seconds: int):
        self._enabled = enabled
        self._buffer_size = buffer_size
        self._ttl = ttl_seconds
        self._store: dict[str, deque[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(self, session_id: str, entry: dict[str, Any]) -> None:
        """Append a trace entry. No-op if disabled."""
        if not self._enabled:
            return
        with self._lock:
            entry = {**entry, "_ts": time.time()}
            dq = self._store.setdefault(
                session_id, deque(maxlen=self._buffer_size)
            )
            dq.append(entry)

    def get(self, session_id: str) -> list[dict[str, Any]]:
        """Return non-expired entries for a session (newest last)."""
        if not self._enabled:
            return []
        cutoff = time.time() - self._ttl
        with self._lock:
            dq = self._store.get(session_id)
            if not dq:
                return []
            fresh = [e for e in dq if e.get("_ts", 0) >= cutoff]
            # Rewrite the deque with only fresh entries.
            self._store[session_id] = deque(fresh, maxlen=self._buffer_size)
            return list(fresh)

    def clear(self, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._store.clear()
            else:
                self._store.pop(session_id, None)


_SINGLETON: DebugTraceBuffer | None = None


def init_trace_buffer(cfg) -> DebugTraceBuffer:
    """Initialize the process-wide trace buffer from DebugConfig."""
    global _SINGLETON
    _SINGLETON = DebugTraceBuffer(
        enabled=cfg.enabled,
        buffer_size=cfg.buffer_size,
        ttl_seconds=cfg.ttl_seconds,
    )
    return _SINGLETON


def get_trace_buffer() -> DebugTraceBuffer:
    """Fetch the singleton. If uninitialized, returns a disabled buffer."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = DebugTraceBuffer(enabled=False, buffer_size=0, ttl_seconds=0)
    return _SINGLETON
