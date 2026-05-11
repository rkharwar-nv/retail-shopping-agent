"""Tests for the in-memory debug trace buffer."""

from __future__ import annotations

import time

from shopping_agent.debug.trace import DebugTraceBuffer


def test_disabled_buffer_is_noop():
    buf = DebugTraceBuffer(enabled=False, buffer_size=10, ttl_seconds=60)
    buf.record("s1", {"x": 1})
    assert buf.get("s1") == []


def test_enabled_buffer_records_and_returns():
    buf = DebugTraceBuffer(enabled=True, buffer_size=10, ttl_seconds=60)
    buf.record("s1", {"turn_id": "t1", "raw": "hello"})
    buf.record("s1", {"turn_id": "t2", "raw": "world"})
    out = buf.get("s1")
    assert len(out) == 2
    assert out[0]["turn_id"] == "t1"
    assert out[1]["turn_id"] == "t2"
    assert "_ts" in out[0]


def test_buffer_size_eviction():
    buf = DebugTraceBuffer(enabled=True, buffer_size=3, ttl_seconds=60)
    for i in range(5):
        buf.record("s1", {"i": i})
    out = buf.get("s1")
    assert len(out) == 3
    assert [e["i"] for e in out] == [2, 3, 4]


def test_ttl_eviction_on_read():
    buf = DebugTraceBuffer(enabled=True, buffer_size=10, ttl_seconds=0)
    buf.record("s1", {"x": 1})
    # ttl=0 means anything recorded before "now" is stale.
    time.sleep(0.01)
    out = buf.get("s1")
    assert out == []


def test_sessions_isolated():
    buf = DebugTraceBuffer(enabled=True, buffer_size=10, ttl_seconds=60)
    buf.record("a", {"x": 1})
    buf.record("b", {"y": 2})
    assert len(buf.get("a")) == 1
    assert len(buf.get("b")) == 1


def test_clear():
    buf = DebugTraceBuffer(enabled=True, buffer_size=10, ttl_seconds=60)
    buf.record("a", {"x": 1})
    buf.record("b", {"y": 2})
    buf.clear("a")
    assert buf.get("a") == []
    assert len(buf.get("b")) == 1
    buf.clear()
    assert buf.get("b") == []
