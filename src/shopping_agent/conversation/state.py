"""M1 stub: in-memory conversation state.

Phase 1 Role-1-only: we record turns and keep a short history per
session. The proper M1 spec (Lesson 3) will flesh this out.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque
from uuid import uuid4

from shopping_agent.gateway.base import MultimodalInput, StructuredUnderstanding


@dataclass
class Turn:
    turn_id: str
    created_at: str
    input: MultimodalInput
    understanding: StructuredUnderstanding | None = None


@dataclass
class Session:
    session_id: str
    created_at: str
    turns: Deque[Turn] = field(default_factory=lambda: deque(maxlen=50))


class SessionStore:
    """Thread-safe in-memory session store.

    A process restart loses state; that's fine for Phase 1. A swap to
    Redis or Postgres later is a sink change, not a caller change."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def ensure_session(self, session_id: str | None) -> Session:
        with self._lock:
            sid = session_id or uuid4().hex
            if sid not in self._sessions:
                self._sessions[sid] = Session(
                    session_id=sid,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            return self._sessions[sid]

    def record_turn(self, session: Session, turn: Turn) -> None:
        with self._lock:
            session.turns.append(turn)

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())
