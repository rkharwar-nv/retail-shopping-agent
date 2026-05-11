"""Tests for the event bus + JSONL sink."""

from __future__ import annotations

import json
from pathlib import Path

from shopping_agent.config import EventsConfig
from shopping_agent.events.bus import build_bus


def test_jsonl_sink_writes_and_reads(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    bus = build_bus(EventsConfig(sink="jsonl_file", path=str(path)))
    bus.publish(
        "turn.received",
        session_id="s1",
        turn_id="t1",
        trace_id="tr1",
        has_text=True,
        image_count=2,
    )
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "turn.received"
    assert payload["session_id"] == "s1"
    assert payload["attrs"]["has_text"] is True
    assert payload["attrs"]["image_count"] == 2
    assert payload["schema_version"] == 1


def test_null_sink_noop():
    bus = build_bus(EventsConfig(sink="null"))
    # Must not raise even with odd data
    bus.publish("whatever", session_id="s", turn_id="t", trace_id="tr", anything=1)


def test_role_fields_promoted(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    bus = build_bus(EventsConfig(sink="jsonl_file", path=str(path)))
    bus.publish(
        "model.call.started",
        session_id="s",
        turn_id="t",
        trace_id="tr",
        role=1,
        provider="nvidia",
        model_id="nvidia/test",
        duration_ms=123,
    )
    payload = json.loads(path.read_text().strip())
    assert payload["role"] == 1
    assert payload["model_id"] == "nvidia/test"
    assert payload["duration_ms"] == 123
    assert "role" not in payload.get("attrs", {})
