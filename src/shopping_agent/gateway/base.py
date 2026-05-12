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


class VideoRef(BaseModel):
    """Reference to a video — URL, local path, or base64."""
    kind: Literal["url", "path", "base64"]
    value: str
    mime_type: str = "video/mp4"


class MultimodalInput(BaseModel):
    """Payload sent to Role 1 (multimodal input adapter)."""
    session_id: str
    turn_id: str
    text: str | None = None
    images: list[ImageRef] = Field(default_factory=list)
    audio: AudioRef | None = None
    videos: list[VideoRef] = Field(default_factory=list)


class DetectedItem(BaseModel):
    """One thing the model noticed in the input (generic fallback)."""
    name: str
    confidence: float | None = None
    source_modality: Literal["image", "audio", "text"]
    attrs: dict[str, Any] = Field(default_factory=dict)


# ─── Vertical-specific perception payloads ───────────────────
#
# One of these gets populated based on the model's classification.
# Each one captures the fields most relevant to its vertical.
# These are DELIBERATELY narrow — they describe what a
# *perception stage* knows, not what a downstream specialist
# will eventually compute. Specialists read these + do more.

PerceptionType = Literal[
    "pantry",
    "shopping_list",
    "food_label",
    "fashion",
    "cosmetics",
    "unknown",
]


class PantryItem(BaseModel):
    """An item observed in a pantry/fridge/ingredients image."""
    name: str
    quantity_hint: str | None = None   # "full bag", "half jar", "2 cans"
    brand: str | None = None
    freshness_hint: str | None = None  # "wilting", "expired", "fresh"
    category: str | None = None        # "produce", "dairy", "grain"
    confidence: float | None = None


class PantryPerception(BaseModel):
    items: list[PantryItem] = Field(default_factory=list)
    overall_coverage: str | None = None  # e.g. "sparse", "well-stocked"
    notable_gaps: list[str] = Field(default_factory=list)
    suggested_recipe_hints: list[str] = Field(default_factory=list)


class ShoppingListLine(BaseModel):
    raw_text: str                       # exactly as written
    normalized_name: str | None = None  # cleaned form
    quantity: str | None = None         # "2 lb", "a dozen"
    category_hint: str | None = None


class ShoppingListPerception(BaseModel):
    items: list[ShoppingListLine] = Field(default_factory=list)
    ambiguous_lines: list[str] = Field(default_factory=list)
    legibility_score: float | None = None  # 0..1


class FoodLabelPerception(BaseModel):
    product_name: str | None = None
    brand: str | None = None
    serving_size: str | None = None
    calories_per_serving: int | None = None
    macros: dict[str, str] = Field(default_factory=dict)  # {"protein": "5g"}
    ingredients_list: list[str] = Field(default_factory=list)
    allergen_callouts: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class FashionItem(BaseModel):
    garment_type: str
    color: str | None = None
    pattern: str | None = None            # "striped", "solid"
    material_guess: str | None = None     # keep conservative
    brand_visible: str | None = None
    style_descriptors: list[str] = Field(default_factory=list)
    size_visible: str | None = None


class FashionPerception(BaseModel):
    primary_item: FashionItem | None = None
    additional_items: list[FashionItem] = Field(default_factory=list)
    occasion_hint: str | None = None


class CosmeticsPerception(BaseModel):
    """Phase 1 stub — cosmetics is classified honestly but not deeply
    extracted until a future phase builds the cosmetics vertical."""
    product_type: str | None = None    # "lipstick", "moisturizer"
    brand: str | None = None
    notes: str | None = None


class StructuredUnderstanding(BaseModel):
    """Role 1 output: typed perception of user input.

    `perception_type` is the discriminator — exactly ONE of the
    typed payload fields (pantry, shopping_list, food_label,
    fashion, cosmetics) should be non-null, matching perception_type.

    `detected_items` remains as a vertical-agnostic fallback so
    code paths that haven't yet been taught to branch on type still
    have something to consume. Populated especially for the
    'unknown' case."""
    schema_version: int = 2
    perception_type: PerceptionType = "unknown"
    perception_confidence: float | None = None

    # Discriminated typed payloads — only one populated.
    pantry: PantryPerception | None = None
    shopping_list: ShoppingListPerception | None = None
    food_label: FoodLabelPerception | None = None
    fashion: FashionPerception | None = None
    cosmetics: CosmeticsPerception | None = None

    # Always-populated, vertical-agnostic fields.
    transcript: str | None = None
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
