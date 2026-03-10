"""Tests for config.py — AppConfig loading and validation."""

import pytest

from config import load_config


def test_config_reads_duckdb_path_from_env(monkeypatch):
    """Config loads DUCKDB_PATH from environment variables."""
    monkeypatch.setenv("DUCKDB_PATH", "/data/threat_hunting.db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    config = load_config()

    assert config.duckdb_path == "/data/threat_hunting.db"


def test_config_default_model_is_gpt_5_4(monkeypatch):
    """Default model is gpt-5.4 when OPENAI_MODEL is unset."""
    monkeypatch.setenv("DUCKDB_PATH", "/data/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = load_config()

    assert config.model == "gpt-5.4"


def test_config_rejects_empty_api_key(monkeypatch):
    """Raises ValueError if OPENAI_API_KEY is empty."""
    monkeypatch.setenv("DUCKDB_PATH", "/data/db")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        load_config()
