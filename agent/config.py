"""Configuration management for the THuntCloud agent.

Provides helpers for reading settings from environment variables.
"""

import os

# Default DuckDB path used when DUCKDB_PATH is not set.
DEFAULT_DUCKDB_PATH: str = "/data/db/threat_hunting.db"


def get_duckdb_path() -> str:
    """Return the DuckDB path from the DUCKDB_PATH environment variable.

    Safe to call without an OpenAI API key — suitable for use in the
    Streamlit agent where the API key is entered via the sidebar UI.

    Returns:
        The value of DUCKDB_PATH if set and non-empty, otherwise
        DEFAULT_DUCKDB_PATH.
    """
    return os.environ.get("DUCKDB_PATH") or DEFAULT_DUCKDB_PATH
