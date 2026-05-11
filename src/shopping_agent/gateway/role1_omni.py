"""M0: Role 1 adapter — Nemotron 3 Nano Omni (multimodal reasoning).

Calls NVIDIA's NIM endpoint at https://integrate.api.nvidia.com/v1
via the OpenAI-compatible chat completions API.

Open questions the spec flagged (confirmed or resolved here will be
noted in SESSION-NOTES.md after first successful call):
  1. Does the endpoint accept OpenAI `/chat/completions` as-is?
  2. What's the exact multimodal content block shape for Omni
     (image_url + text, plus audio somehow)?
  3. Does the model return structured JSON, or prose we re-parse?

This adapter defaults to a robust-but-simple approach:
  - Send text + images as an OpenAI-style multimodal chat request.
  - Ask the model to respond in a known JSON shape (structured output
    via a system prompt).
  - Parse; fall back to putting raw text into `scene_summary` if the
    JSON parse fails, so a malformed first call still produces signal."""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI
from openai import RateLimitError

from shopping_agent.config import ModelRoleConfig
from shopping_agent.events.bus import EventBus
from shopping_agent.events.schema import (
    EV_MODEL_CALL_FAILED,
    EV_MODEL_CALL_STARTED,
    EV_MODEL_CALL_SUCCEEDED,
)
from shopping_agent.gateway.base import (
    DetectedItem,
    ImageRef,
    ModelProviderError,
    ModelRequestError,
    ModelResponseError,
    ModelTimeoutError,
    MultimodalInput,
    StructuredUnderstanding,
)

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the input-processing stage of a retail shopping agent.
You receive the user's message (text, images, and/or audio transcription) and
produce a structured understanding.

Respond ONLY with a JSON object of this shape (no prose, no code fences):

{
  "transcript": "string or null — any audio content transcribed",
  "detected_items": [
    {
      "name": "string — product-like entity observed",
      "source_modality": "image" | "text" | "audio",
      "confidence": 0.0 to 1.0 or null,
      "attrs": { "any": "domain-specific fields" }
    }
  ],
  "scene_summary": "string or null — 1-2 sentence summary of what you see/hear",
  "user_intent_hint": "string or null — best guess at what the user wants"
}

Be concise. No editorial commentary."""


def _image_to_data_url(ref: ImageRef) -> str:
    """OpenAI multimodal requires a data URL or http URL for images."""
    if ref.kind == "url":
        return ref.value
    if ref.kind == "path":
        data = Path(ref.value).read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{ref.mime_type};base64,{b64}"
    if ref.kind == "base64":
        return f"data:{ref.mime_type};base64,{ref.value}"
    raise ValueError(f"Unknown image ref kind: {ref.kind}")


def _extract_json(text: str) -> dict[str, Any]:
    """Models sometimes wrap JSON in prose or code fences. Be forgiving."""
    # strip code fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # first { to last } fallback
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


class Role1OmniAdapter:
    """Nemotron 3 Nano Omni adapter over NVIDIA's OpenAI-compatible NIM."""

    role = 1

    def __init__(self, cfg: ModelRoleConfig, events: EventBus) -> None:
        self._cfg = cfg
        self._events = events
        self._client = AsyncOpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            timeout=cfg.timeout_seconds,
            max_retries=0,  # we control retries ourselves
        )

    async def process(self, inp: MultimodalInput) -> StructuredUnderstanding:
        # Assemble OpenAI-style multimodal content blocks.
        content: list[dict[str, Any]] = []
        if inp.text:
            content.append({"type": "text", "text": inp.text})
        for img in inp.images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _image_to_data_url(img)},
                }
            )
        if inp.audio:
            # TODO(open-q): Omni audio input shape varies by NIM.
            # For now we pass a placeholder text note — audio path is
            # marked as the Lesson-1 open question.
            content.append(
                {
                    "type": "text",
                    "text": f"[audio input attached: {inp.audio.value}]",
                }
            )
        if not content:
            content.append({"type": "text", "text": "(empty input)"})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]

        attempt = 0
        started = time.monotonic()
        ev_common = {
            "session_id": inp.session_id,
            "turn_id": inp.turn_id,
            "trace_id": inp.turn_id,
            "role": self.role,
            "provider": self._cfg.provider,
            "model_id": self._cfg.model_id,
        }
        self._events.publish(EV_MODEL_CALL_STARTED, **ev_common)

        while True:
            attempt += 1
            try:
                resp = await self._client.chat.completions.create(
                    model=self._cfg.model_id,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=0.2,
                    max_tokens=800,
                )
                break
            except APITimeoutError as e:
                if attempt > self._cfg.max_retries:
                    self._events.publish(
                        EV_MODEL_CALL_FAILED,
                        **ev_common,
                        error="timeout",
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                    raise ModelTimeoutError(str(e)) from e
            except RateLimitError as e:
                if attempt > self._cfg.max_retries:
                    self._events.publish(
                        EV_MODEL_CALL_FAILED,
                        **ev_common,
                        error="rate_limited",
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                    raise ModelProviderError(str(e)) from e
            except APIError as e:
                status = getattr(e, "status_code", None)
                if status and 400 <= status < 500:
                    self._events.publish(
                        EV_MODEL_CALL_FAILED,
                        **ev_common,
                        error=f"http_{status}",
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                    raise ModelRequestError(str(e)) from e
                if attempt > self._cfg.max_retries:
                    self._events.publish(
                        EV_MODEL_CALL_FAILED,
                        **ev_common,
                        error=f"http_{status or 'unknown'}",
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                    raise ModelProviderError(str(e)) from e

        duration_ms = int((time.monotonic() - started) * 1000)
        raw_text = (resp.choices[0].message.content or "").strip()

        try:
            parsed = _extract_json(raw_text)
            result = StructuredUnderstanding(
                transcript=parsed.get("transcript"),
                detected_items=[
                    DetectedItem(**d) for d in parsed.get("detected_items", [])
                ],
                scene_summary=parsed.get("scene_summary"),
                user_intent_hint=parsed.get("user_intent_hint"),
                raw_model_metadata={
                    "model": self._cfg.model_id,
                    "usage": getattr(resp, "usage", None).model_dump()
                    if getattr(resp, "usage", None)
                    else None,
                    "finish_reason": resp.choices[0].finish_reason,
                },
            )
        except Exception as e:
            log.warning("Role1 JSON parse failed, falling back to raw: %s", e)
            result = StructuredUnderstanding(
                scene_summary=raw_text[:2000],
                raw_model_metadata={
                    "parse_error": str(e),
                    "model": self._cfg.model_id,
                    "finish_reason": resp.choices[0].finish_reason,
                },
            )

        self._events.publish(
            EV_MODEL_CALL_SUCCEEDED, **ev_common, duration_ms=duration_ms
        )
        return result
