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
    CosmeticsPerception,
    DetectedItem,
    FashionPerception,
    FoodLabelPerception,
    ImageRef,
    ModelProviderError,
    ModelRequestError,
    ModelResponseError,
    ModelTimeoutError,
    MultimodalInput,
    PantryPerception,
    ShoppingListPerception,
    StructuredUnderstanding,
)

log = logging.getLogger(__name__)


STRUCTURAL_OUTPUT_CONTRACT = """First classify the user's input into exactly ONE perception_type:

- "pantry":        food/ingredients/fridge/pantry photo — what the user HAS
- "shopping_list": handwritten or printed list of items the user wants
- "food_label":    nutrition panel, ingredient list, or packaging info panel
- "fashion":       clothing, shoes, accessories, bags, jewelry
- "cosmetics":     skincare, makeup, fragrance, or their labels
- "unknown":       none of the above, or image too unclear

Then populate ONLY the matching typed field. Leave the OTHER typed fields as null.
Always populate scene_summary and user_intent_hint. Populate detected_items as a
flat fallback list (name + source_modality + optional confidence).

Respond ONLY with a JSON object of this exact shape (no prose, no code fences):

{
  "perception_type": "pantry" | "shopping_list" | "food_label" | "fashion" | "cosmetics" | "unknown",
  "perception_confidence": 0.0 to 1.0 or null,

  "pantry": null OR {
    "items": [
      {
        "name": "string",
        "quantity_hint": "string or null",
        "brand": "string or null",
        "freshness_hint": "string or null",
        "category": "string or null",
        "confidence": 0.0 to 1.0 or null
      }
    ],
    "overall_coverage": "string or null",
    "notable_gaps": ["strings"],
    "suggested_recipe_hints": ["strings"]
  },

  "shopping_list": null OR {
    "items": [
      {
        "raw_text": "string",
        "normalized_name": "string or null",
        "quantity": "string or null",
        "category_hint": "string or null"
      }
    ],
    "ambiguous_lines": ["strings"],
    "legibility_score": 0.0 to 1.0 or null
  },

  "food_label": null OR {
    "product_name": "string or null",
    "brand": "string or null",
    "serving_size": "string or null",
    "calories_per_serving": integer or null,
    "macros": { "protein": "5g", "...": "..." },
    "ingredients_list": ["strings"],
    "allergen_callouts": ["strings"],
    "certifications": ["strings"]
  },

  "fashion": null OR {
    "primary_item": {
      "garment_type": "string",
      "color": "string or null",
      "pattern": "string or null",
      "material_guess": "string or null",
      "brand_visible": "string or null",
      "style_descriptors": ["strings"],
      "size_visible": "string or null"
    },
    "additional_items": [ ... same shape as primary_item ... ],
    "occasion_hint": "string or null"
  },

  "cosmetics": null OR {
    "product_type": "string or null",
    "brand": "string or null",
    "notes": "string or null"
  },

  "transcript": "string or null — from audio, if present",
  "detected_items": [
    {
      "name": "string",
      "source_modality": "image" | "audio" | "text",
      "confidence": 0.0 to 1.0 or null,
      "attrs": {}
    }
  ],
  "scene_summary": "string — 1 to 2 sentences",
  "user_intent_hint": "string or null — best guess at what the user wants"
}"""


def _build_system_prompt(cfg: ModelRoleConfig) -> str:
    """Assemble the system prompt: role_instructions → structural
    contract → vertical hints (all of them; model picks after
    classifying) → style."""
    parts: list[str] = []
    role_instr = cfg.prompts.role_instructions.strip()
    style = cfg.prompts.style.strip()
    hints = cfg.prompts.vertical_hints or {}
    if role_instr:
        parts.append(role_instr)
    parts.append(STRUCTURAL_OUTPUT_CONTRACT)
    if hints:
        hint_block = "Per-perception-type extraction guidance (use the one matching your classification):\n\n"
        hint_block += "\n\n".join(
            f"### {k} ###\n{v.strip()}" for k, v in hints.items() if v.strip()
        )
        parts.append(hint_block)
    if style:
        parts.append(style)
    return "\n\n".join(parts)


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
            {"role": "system", "content": _build_system_prompt(self._cfg)},
            {"role": "user", "content": content},
        ]

        gen = self._cfg.generation
        # Build kwargs lazily — don't send None fields.
        call_kwargs: dict[str, Any] = {
            "model": self._cfg.model_id,
            "messages": messages,
            "temperature": gen.temperature,
            "max_tokens": gen.max_tokens,
        }
        if gen.top_p is not None:
            call_kwargs["top_p"] = gen.top_p
        if gen.extras:
            call_kwargs["extra_body"] = gen.extras
        # NOTE: streaming not wired in Phase 1 even if config says true —
        # we consume the full response synchronously. Streaming will be
        # a follow-up when the UI renderer (U1) needs it.

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
                resp = await self._client.chat.completions.create(**call_kwargs)  # type: ignore[arg-type]
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

            # Validate perception_type; anything unrecognized → "unknown".
            perception_type = parsed.get("perception_type", "unknown")
            valid_types = {
                "pantry", "shopping_list", "food_label",
                "fashion", "cosmetics", "unknown",
            }
            if perception_type not in valid_types:
                log.warning(
                    "Role1 unknown perception_type=%r, coercing to 'unknown'",
                    perception_type,
                )
                perception_type = "unknown"

            # Helper: only decode the typed payload matching the
            # declared perception_type. The others are ignored even
            # if the model accidentally populated them — the schema
            # discriminator is our single source of truth.
            def _typed(key: str, model_cls):
                if perception_type != key:
                    return None
                block = parsed.get(key)
                if not isinstance(block, dict):
                    return None
                try:
                    return model_cls(**block)
                except Exception as typed_e:  # noqa: BLE001
                    log.warning(
                        "Role1 typed payload %s failed to validate: %s",
                        key, typed_e,
                    )
                    return None

            result = StructuredUnderstanding(
                perception_type=perception_type,  # type: ignore[arg-type]
                perception_confidence=parsed.get("perception_confidence"),
                pantry=_typed("pantry", PantryPerception),
                shopping_list=_typed("shopping_list", ShoppingListPerception),
                food_label=_typed("food_label", FoodLabelPerception),
                fashion=_typed("fashion", FashionPerception),
                cosmetics=_typed("cosmetics", CosmeticsPerception),
                transcript=parsed.get("transcript"),
                detected_items=[
                    DetectedItem(**d) for d in parsed.get("detected_items", [])
                    if isinstance(d, dict)
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
                perception_type="unknown",
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

        # Debug trace capture — only records if debug.enabled is true.
        # Lives in memory; exposed via /debug/trace/<session_id>.
        try:
            from shopping_agent.debug.trace import get_trace_buffer

            buf = get_trace_buffer()
            if buf.enabled:
                # Build a redacted copy of the messages for trace: keep
                # system prompt + user text, summarize images/audio as
                # metadata instead of serializing base64 blobs.
                user_content_trace = []
                for part in content:
                    if part.get("type") == "text":
                        user_content_trace.append(part)
                    elif part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            header = url.split(",", 1)[0]
                            user_content_trace.append({
                                "type": "image_url",
                                "url_kind": "base64_data_url",
                                "header": header,
                                "approx_bytes": len(url),
                            })
                        else:
                            user_content_trace.append({
                                "type": "image_url", "url": url,
                            })
                    else:
                        user_content_trace.append({"type": part.get("type", "?")})

                buf.record(
                    inp.session_id,
                    {
                        "turn_id": inp.turn_id,
                        "role": self.role,
                        "model_id": self._cfg.model_id,
                        "provider": self._cfg.provider,
                        "duration_ms": duration_ms,
                        "system_prompt_assembled": _build_system_prompt(self._cfg),
                        "user_message_trace": user_content_trace,
                        "upstream_request": {
                            k: v for k, v in call_kwargs.items() if k != "messages"
                        },
                        "upstream_response_raw": raw_text,
                        "usage": (
                            resp.usage.model_dump()
                            if getattr(resp, "usage", None) else None
                        ),
                        "finish_reason": resp.choices[0].finish_reason,
                    },
                )
        except Exception as trace_err:  # noqa: BLE001
            log.debug("debug trace record failed: %s", trace_err)

        return result
