"""Tests for the broadcaster + stats aggregator."""

from __future__ import annotations

from shopping_agent.events.broadcaster import BroadcastSink, aggregate_stats
from shopping_agent.events.schema import Event


def _mk(event_type, **kw):
    return Event(
        event_type=event_type,
        session_id=kw.get("sid", "s1"),
        turn_id=kw.get("tid", "t1"),
        trace_id=kw.get("trid", "x1"),
        role=kw.get("role"),
        model_id=kw.get("model_id"),
        duration_ms=kw.get("duration_ms"),
        attrs=kw.get("attrs") or {},
    )


def test_broadcast_forwards_and_fans_out():
    seen = []

    class _Inner:
        def write(self, e):
            seen.append(e)

    sink = BroadcastSink(_Inner())
    received = []
    off = sink.subscribe(received.append)
    sink.write(_mk("model.call.succeeded", role=1,
                   model_id="m", duration_ms=10))
    assert len(seen) == 1
    assert len(received) == 1
    off()
    sink.write(_mk("model.call.succeeded"))
    assert len(seen) == 2
    assert len(received) == 1  # unsubscribed


def test_history_scoped_by_session():
    class _Inner:
        def write(self, e):  # noqa: ARG002
            pass

    sink = BroadcastSink(_Inner())
    sink.write(_mk("model.call.succeeded", sid="s1", role=1, model_id="m"))
    sink.write(_mk("model.call.succeeded", sid="s2", role=1, model_id="m"))
    sink.write(_mk("model.call.succeeded", sid="s1", role=1, model_id="m"))
    assert len(sink.history("s1")) == 2
    assert len(sink.history("s2")) == 1
    assert sink.history("nope") == []


def test_aggregate_stats_counts_calls_tokens_latency():
    events = [
        _mk("model.call.started", role=1, model_id="m1"),
        _mk("model.call.succeeded", role=1, model_id="m1",
            duration_ms=1000, attrs={"usage": {"prompt_tokens": 100,
                                                "completion_tokens": 50,
                                                "reasoning_tokens": 10}}),
        _mk("model.call.succeeded", role=1, model_id="m1",
            duration_ms=2000, attrs={"usage": {"prompt_tokens": 200,
                                                "completion_tokens": 80}}),
    ]
    stats = aggregate_stats(events)
    assert stats["calls_by_role"] == {"role1": 2}
    m = stats["calls_by_model"]["m1"]
    assert m["calls"] == 2
    assert m["prompt_tokens"] == 300
    assert m["completion_tokens"] == 130
    assert m["reasoning_tokens"] == 10
    assert m["total_latency_ms"] == 3000
    assert "role1" in stats["agents_active"]
    assert stats["sub_agents"] == []
    assert len(stats["timeline"]) >= 3
