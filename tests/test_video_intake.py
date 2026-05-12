"""Tests for the Role 1 video-intake path — all mocked, no network."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from shopping_agent.config import EventsConfig, ModelRoleConfig
from shopping_agent.events.bus import build_bus
from shopping_agent.gateway.base import MultimodalInput, VideoRef
from shopping_agent.gateway.role1_omni import Role1OmniAdapter


class _FakeChoice:
    def __init__(self, content: str):
        self.message = type("M", (), {"content": content})()
        self.finish_reason = "stop"


class _FakeResp:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = None


def test_video_ref_serializes():
    ref = VideoRef(kind="base64", value="aGVsbG8=", mime_type="video/mp4")
    dumped = ref.model_dump()
    restored = VideoRef(**dumped)
    assert restored == ref
    assert dumped["kind"] == "base64"
    assert dumped["value"] == "aGVsbG8="
    assert dumped["mime_type"] == "video/mp4"


def test_chat_request_accepts_videos():
    mi = MultimodalInput(
        session_id="s1",
        turn_id="t1",
        text="hi",
        videos=[VideoRef(kind="base64", value="aGVsbG8=", mime_type="video/mp4")],
    )
    assert len(mi.videos) == 1
    assert mi.videos[0].mime_type == "video/mp4"
    # No spillover into other modalities.
    assert mi.images == []
    assert mi.audio is None


@pytest.mark.asyncio
async def test_role1_adapter_builds_video_content_block(monkeypatch):
    cfg = ModelRoleConfig(
        provider="test",
        base_url="https://example.invalid/v1",
        model_id="nvidia/test",
        api_key_env="TEST_R1",
    )
    monkeypatch.setenv("TEST_R1", "fake")
    bus = build_bus(EventsConfig(sink="null"))
    adapter = Role1OmniAdapter(cfg, bus)

    mock_create = AsyncMock(return_value=_FakeResp('{"scene_summary": "ok"}'))
    adapter._client.chat.completions.create = mock_create

    await adapter.process(
        MultimodalInput(
            session_id="s",
            turn_id="t",
            text="what is this clip?",
            videos=[
                VideoRef(kind="base64", value="aGVsbG8=", mime_type="video/mp4"),
            ],
        )
    )

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    user_msg = kwargs["messages"][1]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    assert isinstance(content, list)

    video_blocks = [c for c in content if c.get("type") == "video_url"]
    assert len(video_blocks) == 1
    block = video_blocks[0]
    assert "video_url" in block
    url = block["video_url"]["url"]
    assert url.startswith("data:video/mp4;base64,")
    assert url.endswith("aGVsbG8=")
