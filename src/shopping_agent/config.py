"""M-SEC: config loader.

Non-secret settings come from config.yaml in the working directory.
Secret API keys come from environment variables named in that yaml.
Loader fails fast at startup if any required key is missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelRoleConfig(BaseModel):
    """Config for one model role (Role 1, 2, or 3)."""

    provider: str
    base_url: str
    model_id: str
    api_key_env: str = Field(..., description="Env var holding the secret API key")
    timeout_seconds: int = 30
    max_retries: int = 2

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


class AppConfig(BaseModel):
    """Top-level application config. Loaded once at startup."""

    schema_version: int = 1
    models: ModelsConfig
    events: EventsConfig = EventsConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    catalog: CatalogConfig = CatalogConfig()
    hooks: HooksConfig = HooksConfig()

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
