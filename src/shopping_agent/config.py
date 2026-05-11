"""M-SEC: config loader.

Non-secret settings come from config.yaml in the working directory.
Secret API keys come from environment variables named in that yaml.
Loader fails fast at startup if any required key is missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class GenerationConfig(BaseModel):
    """Model-tuning knobs. Per-role overridable.

    These are PROVIDER-AGNOSTIC knobs (temperature, top_p, max_tokens,
    stream). Provider-specific fields (e.g. NVIDIA's reasoning flags)
    live in `extras`, which is passed straight through to the provider
    as `extra_body` if the adapter supports it.
    """

    temperature: float = 0.2
    top_p: float | None = None
    max_tokens: int = 800
    stream: bool = False
    # Provider-specific body extensions. Merged into the SDK call as-is.
    # Keep this last — when we swap providers, the generic knobs stay
    # but `extras` almost always changes.
    extras: dict[str, Any] = Field(default_factory=dict)


class PromptsConfig(BaseModel):
    """Behavioral prompt fragments. The STRUCTURAL output contract
    lives in code next to the parser — that's not config."""

    role_instructions: str = ""
    style: str = ""
    # Per-perception-type extraction emphasis. Keys should match
    # PerceptionType values (pantry, shopping_list, food_label,
    # fashion, cosmetics). All are optional — omit or leave blank
    # to use the structural contract alone.
    vertical_hints: dict[str, str] = Field(default_factory=dict)


class ModelRoleConfig(BaseModel):
    """Config for one model role (Role 1, 2, or 3)."""

    provider: str
    base_url: str
    model_id: str
    api_key_env: str = Field(..., description="Env var holding the secret API key")
    timeout_seconds: int = 30
    max_retries: int = 2
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)

    @property
    def api_key(self) -> str:
        """Resolve the API key at call time (not at config load)."""
        value = os.environ.get(self.api_key_env, "").strip()
        if not value or value.startswith("nvapi-REPLACE"):
            raise RuntimeError(
                f"Required env var {self.api_key_env} is unset or still a placeholder. "
                f"Copy .env.example to .env and fill in real values."
            )
        return value


class ModelsConfig(BaseModel):
    role1: ModelRoleConfig
    role2: ModelRoleConfig
    role3: ModelRoleConfig


class EventsConfig(BaseModel):
    sink: Literal["jsonl_file", "stdout", "null"] = "jsonl_file"
    path: str = "./events/events.jsonl"
    non_blocking: bool = True


class VectorStoreConfig(BaseModel):
    driver: Literal["pgvector", "memory", "none"] = "pgvector"


class CatalogConfig(BaseModel):
    source: Literal["hybrid", "synthetic", "public"] = "hybrid"
    seed_size: int = 1000


class HooksConfig(BaseModel):
    guardrails: Literal["noop"] = "noop"
    profile: Literal["empty"] = "empty"
    consent: Literal["always_granted"] = "always_granted"


class DebugConfig(BaseModel):
    """In-memory upstream-call trace for developer introspection.

    SECURITY: keep `enabled: false` in any shared or production
    environment. Traces hold raw model prompts and raw model
    responses — sensitive by default.
    """

    enabled: bool = False
    # Max entries kept in the in-memory ring buffer per session.
    buffer_size: int = 20
    # Entries older than this are evicted on read.
    ttl_seconds: int = 300


class AppConfig(BaseModel):
    """Top-level application config. Loaded once at startup."""

    schema_version: int = 1
    models: ModelsConfig
    events: EventsConfig = EventsConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    catalog: CatalogConfig = CatalogConfig()
    hooks: HooksConfig = HooksConfig()
    debug: DebugConfig = DebugConfig()

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, v: int) -> int:
        if v != 1:
            raise ValueError(
                f"config.yaml has schema_version={v}, this build expects 1"
            )
        return v


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load config.yaml. Falls back to config.example.yaml ONLY for dev
    smoke-tests, never in production behavior — caller decides."""
    if path is None:
        path = Path("config.yaml")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy config.example.yaml to config.yaml "
            f"and adjust as needed."
        )
    with path.open("r") as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig(**raw)


def verify_secrets(cfg: AppConfig) -> None:
    """Force-resolve every API key so missing ones fail at startup, not
    at first call. M-SEC rule: fail fast."""
    _ = cfg.models.role1.api_key
    _ = cfg.models.role2.api_key
    _ = cfg.models.role3.api_key
