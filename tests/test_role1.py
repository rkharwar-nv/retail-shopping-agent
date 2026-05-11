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

    # Pantry-classified response with typed payload.
    fake_content = json.dumps(
        {
            "perception_type": "pantry",
            "perception_confidence": 0.85,
            "pantry": {
                "items": [
                    {"name": "milk", "quantity_hint": "half gallon",
                     "category": "dairy", "confidence": 0.9},
                    {"name": "eggs", "quantity_hint": "6 eggs",
                     "category": "dairy", "confidence": 0.95},
                ],
                "overall_coverage": "sparse",
                "notable_gaps": ["bread", "vegetables"],
                "suggested_recipe_hints": ["scrambled eggs", "french toast"],
            },
            "shopping_list": None,
            "food_label": None,
            "fashion": None,
            "cosmetics": None,
            "transcript": None,
            "detected_items": [
                {"name": "milk", "source_modality": "image", "confidence": 0.9},
                {"name": "eggs", "source_modality": "image", "confidence": 0.95},
            ],
            "scene_summary": "A fridge with milk and eggs.",
            "user_intent_hint": "meal planning",
        }
    )
    adapter._client.chat.completions.create = AsyncMock(
        return_value=_FakeResp(fake_content)
    )

    result = await adapter.process(
        MultimodalInput(session_id="s", turn_id="t", text="what's in there?")
    )
    assert result.perception_type == "pantry"
    assert result.perception_confidence == 0.85
    assert result.pantry is not None
    assert len(result.pantry.items) == 2
    assert result.pantry.items[0].name == "milk"
    assert result.pantry.overall_coverage == "sparse"
    assert "bread" in result.pantry.notable_gaps
    # Other typed payloads stay None.
    assert result.shopping_list is None
    assert result.food_label is None
    assert result.fashion is None
    # Vertical-agnostic fallbacks still populated.
    assert result.scene_summary == "A fridge with milk and eggs."
    assert len(result.detected_items) == 2


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


@pytest.mark.asyncio
async def test_role1_passes_config_knobs_to_client(monkeypatch):
    """Generation config (temperature, top_p, max_tokens, extras) and
    the assembled system prompt all reach the underlying SDK call.

    This test protects the contract between config.yaml and what
    actually hits NVIDIA's API. If someone 'simplifies' the adapter
    by hardcoding again, this test breaks and reminds them why."""
    from shopping_agent.config import GenerationConfig, PromptsConfig

    cfg = ModelRoleConfig(
        provider="test",
        base_url="https://example.invalid/v1",
        model_id="nvidia/test",
        api_key_env="TEST_R1",
        generation=GenerationConfig(
            temperature=0.6,
            top_p=0.95,
            max_tokens=32768,
            extras={
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": 16384,
            },
        ),
        prompts=PromptsConfig(
            role_instructions="You are a grocery perception agent.",
            style="Be concise.",
        ),
    )
    monkeypatch.setenv("TEST_R1", "fake")
    bus = build_bus(EventsConfig(sink="null"))
    adapter = Role1OmniAdapter(cfg, bus)

    mock_create = AsyncMock(return_value=_FakeResp('{"scene_summary": "ok"}'))
    adapter._client.chat.completions.create = mock_create

    await adapter.process(
        MultimodalInput(session_id="s", turn_id="t", text="test")
    )

    # Verify the SDK got called with everything config specified.
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["temperature"] == 0.6
    assert kwargs["top_p"] == 0.95
    assert kwargs["max_tokens"] == 32768
    assert kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": 16384,
    }
    # System prompt assembled from: role_instructions + structural
    # contract + style. All three fragments must appear.
    system_msg = kwargs["messages"][0]["content"]
    assert "grocery perception agent" in system_msg
    assert '"detected_items"' in system_msg  # the structural contract
    assert "Be concise." in system_msg


@pytest.mark.asyncio
async def test_role1_shopping_list_classification(monkeypatch):
    """Handwritten list returns shopping_list payload, pantry stays None."""
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
            "perception_type": "shopping_list",
            "perception_confidence": 0.9,
            "pantry": None,
            "shopping_list": {
                "items": [
                    {"raw_text": "2 lb chkn", "normalized_name": "chicken",
                     "quantity": "2 lb", "category_hint": "protein"},
                    {"raw_text": "milk", "normalized_name": "milk, 1 gallon"},
                ],
                "ambiguous_lines": [],
                "legibility_score": 0.8,
            },
            "food_label": None, "fashion": None, "cosmetics": None,
            "transcript": None,
            "detected_items": [],
            "scene_summary": "A handwritten shopping list.",
            "user_intent_hint": "grocery run",
        }
    )
    adapter._client.chat.completions.create = AsyncMock(
        return_value=_FakeResp(fake_content)
    )
    result = await adapter.process(
        MultimodalInput(session_id="s", turn_id="t", text="")
    )
    assert result.perception_type == "shopping_list"
    assert result.shopping_list is not None
    assert len(result.shopping_list.items) == 2
    assert result.shopping_list.items[0].normalized_name == "chicken"
    assert result.shopping_list.legibility_score == 0.8
    assert result.pantry is None  # discrimination holds


@pytest.mark.asyncio
async def test_role1_discriminator_ignores_other_payloads(monkeypatch):
    """If the model fills MULTIPLE typed payloads (shouldn't, but might),
    only the one matching perception_type is kept."""
    cfg = ModelRoleConfig(
        provider="test", base_url="https://example.invalid/v1",
        model_id="nvidia/test", api_key_env="TEST_R1",
    )
    monkeypatch.setenv("TEST_R1", "fake")
    bus = build_bus(EventsConfig(sink="null"))
    adapter = Role1OmniAdapter(cfg, bus)

    # Model claims pantry, but ALSO fills fashion. We must ignore fashion.
    fake_content = json.dumps(
        {
            "perception_type": "pantry",
            "pantry": {"items": [{"name": "apple"}]},
            "fashion": {"primary_item": {"garment_type": "t-shirt"}},
            "scene_summary": "An apple.", "user_intent_hint": "snack",
            "detected_items": [],
        }
    )
    adapter._client.chat.completions.create = AsyncMock(
        return_value=_FakeResp(fake_content)
    )
    result = await adapter.process(
        MultimodalInput(session_id="s", turn_id="t", text="")
    )
    assert result.perception_type == "pantry"
    assert result.pantry is not None
    assert result.fashion is None  # stray payload dropped by discriminator


@pytest.mark.asyncio
async def test_role1_unknown_perception_type_coerced(monkeypatch):
    """Bogus perception_type from model gets coerced to 'unknown'."""
    cfg = ModelRoleConfig(
        provider="test", base_url="https://example.invalid/v1",
        model_id="nvidia/test", api_key_env="TEST_R1",
    )
    monkeypatch.setenv("TEST_R1", "fake")
    bus = build_bus(EventsConfig(sink="null"))
    adapter = Role1OmniAdapter(cfg, bus)

    fake_content = json.dumps(
        {
            "perception_type": "kitchenware",  # not in taxonomy
            "scene_summary": "a spatula", "user_intent_hint": None,
            "detected_items": [],
        }
    )
    adapter._client.chat.completions.create = AsyncMock(
        return_value=_FakeResp(fake_content)
    )
    result = await adapter.process(
        MultimodalInput(session_id="s", turn_id="t", text="")
    )
    assert result.perception_type == "unknown"
