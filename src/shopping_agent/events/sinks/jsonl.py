"""M-EVENTS: JSONL file sink.

Phase 1 implementation. Appends each event as a single JSON line.
Non-blocking in the sense that file write errors never raise to the
caller — they're swallowed and counted."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from shopping_agent.events.schema import Event


class JsonlFileSink:
    """Append-only JSONL file sink. Thread-safe via a lock."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._dropped = 0

    def write(self, event: Event) -> None:
        try:
            line = event.model_dump_json(exclude_none=True)
            with self._lock, self._path.open("a") as f:
                f.write(line + "\n")
        except Exception:
            # M-EVENTS invariant: bus failure never blocks a turn.
            self._dropped += 1

    @property
    def dropped_count(self) -> int:
        return self._dropped

    @property
    def path(self) -> Path:
        return self._path
