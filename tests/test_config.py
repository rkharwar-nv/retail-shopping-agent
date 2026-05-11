"""Tests for the M-SEC config loader."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from shopping_agent.config import load_config, verify_secrets


def test_load_config_happy(tmp_yaml: Path, env_keys, monkeypatch):
    monkeypatch.chdir(tmp_yaml)
    cfg = load_config()
    assert cfg.schema_version == 1
    assert cfg.models.role1.model_id == "test/role1"
    assert cfg.models.role3.api_key_env == "TEST_ROLE3_KEY"


def test_verify_secrets_fails_when_missing(tmp_yaml: Path, monkeypatch):
    monkeypatch.chdir(tmp_yaml)
    monkeypatch.delenv("TEST_ROLE1_KEY", raising=False)
    monkeypatch.setenv("TEST_ROLE2_KEY", "x")
    monkeypatch.setenv("TEST_ROLE3_KEY", "x")
    cfg = load_config()
    with pytest.raises(RuntimeError, match="TEST_ROLE1_KEY"):
        verify_secrets(cfg)


def test_verify_secrets_rejects_placeholder(tmp_yaml: Path, monkeypatch):
    monkeypatch.chdir(tmp_yaml)
    monkeypatch.setenv("TEST_ROLE1_KEY", "nvapi-REPLACE_ME")
    monkeypatch.setenv("TEST_ROLE2_KEY", "x")
    monkeypatch.setenv("TEST_ROLE3_KEY", "x")
    cfg = load_config()
    with pytest.raises(RuntimeError, match="placeholder"):
        verify_secrets(cfg)


def test_missing_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_config()
