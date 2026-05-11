"""Tests for Role 1 adapter — all mocked, no network."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from shopping_agent.config import EventsConfig, ModelRoleConfig
from shopping_agent.events.bus import build_bus
from shopping_agent.gateway.base import ImageRef, MultimodalInput
from shopping_agent.gateway.role1_omni import Role1OmniAdapter, _extract_json


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = '```json\n{"a": 1}\n```'
    assert _extract_json(text) == {"a": 1}


def test_extract_json_with_prose():
    text = 'Sure! Here you go:\n{"a": 1, "b": [2,3]}\nHope that helps.'
    assert _extract_json(text) == {"a": 1, "b": [2, 3]}


class _FakeChoice:
    def __init__(self, content: str):
        self.message = type("M", (), {"content": content})()
        self.finish_reason = "stop"


class _FakeResp:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = None


@pytest.mark.asyncio
async def test_role1_parses_json_response(monkeypatch, tmp_path):
    cfg = ModelRoleConfig(
        provider="test",
        base_url="https://example.invalid/v1",
        model_id="nvidia/test",
        api_key_env="TEST_R1",
    )
    monkeypatch.setenv("TEST_R1", "fake")
    bus = build_bus(EventsConfig(sink="null"))
    adapter = Role1OmniAdapter(cfg, bus)

    fake_content = json.dumps(
        {
            "transcript": None,
            "detected_items": [
                {"name": "milk", "source_modality": "image", "confidence": 0.9}
            ],
            "scene_summary": "A fridge.",
            "user_intent_hint": "meal planning",
        }
    )
    adapter._client.chat.completions.create = AsyncMock(
        return_value=_FakeResp(fake_content)
    )

    result = await adapter.process(
        MultimodalInput(session_id="s", turn_id="t", text="what's in there?")
    )
    assert result.scene_summary == "A fridge."
    assert len(result.detected_items) == 1
    assert result.detected_items[0].name == "milk"


@pytest.mark.asyncio
async def test_role1_falls_back_to_raw_on_malformed_json(monkeypatch):
    cfg = ModelRoleConfig(
        provider="test",
        base_url="https://example.invalid/v1",
        model_id="nvidia/test",
        api_key_env="TEST_R1",
    )
    monkeypatch.setenv("TEST_R1", "fake")
    bus = build_bus(EventsConfig(sink="null"))
    adapter = Role1OmniAdapter(cfg, bus)

    adapter._client.chat.completions.create = AsyncMock(
        return_value=_FakeResp("sorry I can't help with that")
    )

    result = await adapter.process(
        MultimodalInput(session_id="s", turn_id="t", text="hi")
    )
    assert result.scene_summary == "sorry I can't help with that"
    assert result.detected_items == []
    assert "parse_error" in result.raw_model_metadata
