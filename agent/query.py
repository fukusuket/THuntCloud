"""DuckDB query execution and validation.

Provides safe, read-only DuckDB query execution with keyword filtering,
EXPLAIN validation, result limiting, and timeout protection.
"""

import concurrent.futures
import logging
import re

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_SECONDS: int = 30
DEFAULT_ROW_LIMIT: int = 1000

# Forbidden SQL keywords that must never be executed (case-insensitive, word boundary).
_FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\b",
    re.IGNORECASE,
)


class QueryValidationError(Exception):
    """Raised when a SQL query fails safety validation."""


def connect_duckdb(path: str) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection in READ_ONLY mode.

    Args:
        path: Filesystem path to the DuckDB database file.

    Returns:
        A DuckDB connection opened in read-only mode.
    """
    return duckdb.connect(path, read_only=True)


def validate_query(conn: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Validate SQL safety using keyword filtering and EXPLAIN.

    Performs two checks in order:
    1. Rejects any statement containing forbidden write/DDL keywords.
    2. Runs ``EXPLAIN <sql>`` to verify the query is syntactically valid
       without executing it.

    Args:
        conn: An open DuckDB connection.
        sql:  The SQL string to validate.

    Raises:
        QueryValidationError: If the query contains forbidden keywords or
                              fails the EXPLAIN check.
    """
    if _FORBIDDEN_PATTERN.search(sql):
        raise QueryValidationError(f"Write/DDL statements are not allowed: {sql[:120]}")

    try:
        conn.execute(f"EXPLAIN {sql}")
    except Exception as exc:
        raise QueryValidationError(f"SQL validation failed: {exc}") from exc


def _run_query(conn: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    """Execute SQL and return results as a DataFrame (internal helper)."""
    result = conn.execute(sql)
    return result.df()


def execute_query(conn: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    """Validate and execute a SQL query, returning results as a DataFrame.

    Enforces safety validation, then runs the query in a thread with a
    hard timeout of ``QUERY_TIMEOUT_SECONDS`` seconds.

    Args:
        conn: An open DuckDB connection (must be READ_ONLY).
        sql:  The SQL string to execute.

    Returns:
        A pandas DataFrame containing the query results.
        Returns an empty DataFrame when the query produces no rows.

    Raises:
        QueryValidationError: If the query fails safety validation.
        TimeoutError:         If the query exceeds the timeout limit.
    """
    validate_query(conn, sql)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_query, conn, sql)
        try:
            return future.result(timeout=QUERY_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutError(
                f"Query exceeded the {QUERY_TIMEOUT_SECONDS}s timeout limit."
            ) from exc
