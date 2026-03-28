"""Tests for config.py — get_duckdb_path and DEFAULT_DUCKDB_PATH."""

from config import DEFAULT_DUCKDB_PATH, get_duckdb_path


# ---------------------------------------------------------------------------
# Tests for get_duckdb_path()
# ---------------------------------------------------------------------------


def test_get_duckdb_path_returns_env_var(monkeypatch):
    """get_duckdb_path() returns the DUCKDB_PATH env var when set."""
    monkeypatch.setenv("DUCKDB_PATH", "/custom/path.db")
    assert get_duckdb_path() == "/custom/path.db"


def test_get_duckdb_path_returns_default_when_unset(monkeypatch):
    """get_duckdb_path() returns DEFAULT_DUCKDB_PATH when DUCKDB_PATH is not set."""
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    assert get_duckdb_path() == DEFAULT_DUCKDB_PATH


def test_get_duckdb_path_returns_default_when_empty(monkeypatch):
    """get_duckdb_path() falls back to DEFAULT_DUCKDB_PATH when DUCKDB_PATH is empty string."""
    monkeypatch.setenv("DUCKDB_PATH", "")
    assert get_duckdb_path() == DEFAULT_DUCKDB_PATH


def test_default_duckdb_path_constant():
    """DEFAULT_DUCKDB_PATH must point to the standard Docker container path."""
    assert DEFAULT_DUCKDB_PATH == "/data/db/threat_hunting.db"
