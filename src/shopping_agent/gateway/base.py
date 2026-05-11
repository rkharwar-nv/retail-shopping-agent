"""M0: gateway base types.

Defines the adapter interfaces shared across Role 1 (multimodal
input), Role 2 (reasoning + tool calling), and Role 3 (embeddings).

Keeping role-specific types in role-specific modules and shared
types here. Adapters should never import each other."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


# ─── Role 1 types ────────────────────────────────────────────

class ImageRef(BaseModel):
    """Reference to an image — URL, local path, or base64."""
    kind: Literal["url", "path", "base64"]
    value: str
    mime_type: str = "image/jpeg"


class AudioRef(BaseModel):
    """Reference to an audio sample."""
    kind: Literal["url", "path", "base64"]
    value: str
    mime_type: str = "audio/wav"


class MultimodalInput(BaseModel):
    """Payload sent to Role 1 (multimodal input adapter)."""
    session_id: str
    turn_id: str
    text: str | None = None
    images: list[ImageRef] = Field(default_factory=list)
    audio: AudioRef | None = None


class DetectedItem(BaseModel):
    """One thing the model noticed in the input."""
    name: str
    confidence: float | None = None
    source_modality: Literal["image", "audio", "text"]
    attrs: dict[str, Any] = Field(default_factory=dict)


class StructuredUnderstanding(BaseModel):
    """Role 1 output: structured interpretation of user input."""
    schema_version: int = 1
    transcript: str | None = None            # ASR output if audio given
    detected_items: list[DetectedItem] = Field(default_factory=list)
    scene_summary: str | None = None
    user_intent_hint: str | None = None
    raw_model_metadata: dict[str, Any] = Field(default_factory=dict)


# ─── Adapter protocols ───────────────────────────────────────

class InputProcessingAdapter(Protocol):
    """Role 1."""
    async def process(self, inp: MultimodalInput) -> StructuredUnderstanding: ...


# Role 2 and Role 3 adapter protocols will be added alongside their
# implementations. Keeping this file lean until then.


# ─── Exceptions ──────────────────────────────────────────────

class ModelError(RuntimeError):
    """Base class for model-layer failures."""


class ModelTimeoutError(ModelError):
    """Terminal timeout after configured retries."""


class ModelRequestError(ModelError):
    """4xx from provider. Not retried."""


class ModelProviderError(ModelError):
    """5xx or transport-level failure after retries."""


class ModelResponseError(ModelError):
    """Provider returned something we can't parse."""
