"""Shared test fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_yaml(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text(
        """
schema_version: 1
models:
  role1:
    provider: test
    base_url: https://example.invalid/v1
    model_id: test/role1
    api_key_env: TEST_ROLE1_KEY
  role2:
    provider: test
    base_url: https://example.invalid/v1
    model_id: test/role2
    api_key_env: TEST_ROLE2_KEY
  role3:
    provider: test
    base_url: https://example.invalid/v1
    model_id: test/role3
    api_key_env: TEST_ROLE3_KEY
events:
  sink: "null"
""".strip()
    )
    return tmp_path


@pytest.fixture
def env_keys(monkeypatch):
    monkeypatch.setenv("TEST_ROLE1_KEY", "test-key-1")
    monkeypatch.setenv("TEST_ROLE2_KEY", "test-key-2")
    monkeypatch.setenv("TEST_ROLE3_KEY", "test-key-3")
