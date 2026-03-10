"""Configuration management for the THuntCloud agent.

Loads settings from environment variables and validates required fields.
"""

import os
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    """Application configuration loaded from environment variables."""

    duckdb_path: str
    api_key: str
    model: str = field(default="gpt-5.4")
    model_lite: str = field(default="gpt-5.4-mini")
    readonly: bool = field(default=True)

    def __post_init__(self) -> None:
        """Validate required fields after initialization."""
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must not be empty")
        if not self.duckdb_path:
            raise ValueError("DUCKDB_PATH must not be empty")


def load_config() -> AppConfig:
    """Load AppConfig from environment variables.

    Required environment variables:
        DUCKDB_PATH     -- Path to the DuckDB database file.
        OPENAI_API_KEY  -- OpenAI API key.

    Optional environment variables:
        OPENAI_MODEL      -- Model for SQL generation (default: gpt-5.4).
        OPENAI_MODEL_LITE -- Lightweight model (default: gpt-5.4-mini).
        DUCKDB_READONLY   -- Must be 'true' for agent (default: true).
    """
    return AppConfig(
        duckdb_path=os.environ.get("DUCKDB_PATH", ""),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_MODEL", "gpt-5.4"),
        model_lite=os.environ.get("OPENAI_MODEL_LITE", "gpt-5.4-mini"),
        readonly=os.environ.get("DUCKDB_READONLY", "true").lower() == "true",
    )
