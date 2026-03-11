"""Tests for query.py — DuckDB query execution and validation."""

import concurrent.futures

import pandas as pd
import pytest

from query import (
    DEFAULT_ROW_LIMIT,
    QueryValidationError,
    apply_row_limit,
    connect_duckdb,
    execute_query,
    validate_query,
)


def test_connect_duckdb_readonly(tmp_duckdb):
    """Opens DuckDB in read-only mode successfully."""
    conn = connect_duckdb(tmp_duckdb)

    assert conn is not None
    conn.close()


def test_execute_select_query(tmp_duckdb):
    """Executes a simple SELECT and returns a pandas DataFrame."""
    conn = connect_duckdb(tmp_duckdb)

    df = execute_query(conn, "SELECT event_name FROM cloudtrail_events LIMIT 5")

    assert isinstance(df, pd.DataFrame)
    assert "event_name" in df.columns
    assert len(df) > 0
    conn.close()


def test_execute_query_returns_empty_dataframe_for_no_results(tmp_duckdb):
    """Empty result returns an empty DataFrame, not an error."""
    conn = connect_duckdb(tmp_duckdb)

    df = execute_query(
        conn,
        "SELECT event_name FROM cloudtrail_events WHERE event_name = '__no_such_event__'",
    )

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    conn.close()


def test_validate_query_with_explain(tmp_duckdb):
    """Running EXPLAIN before execution does not raise on valid SQL."""
    conn = connect_duckdb(tmp_duckdb)

    # Should not raise
    validate_query(conn, "SELECT event_name FROM cloudtrail_events LIMIT 10")

    conn.close()


def test_validate_query_rejects_write_statements(tmp_duckdb):
    """INSERT, UPDATE, DELETE, DROP statements are rejected before execution."""
    conn = connect_duckdb(tmp_duckdb)

    forbidden = [
        "INSERT INTO cloudtrail_events (event_name) VALUES ('x')",
        "UPDATE cloudtrail_events SET event_name = 'x'",
        "DELETE FROM cloudtrail_events",
        "DROP TABLE cloudtrail_events",
        "ALTER TABLE cloudtrail_events ADD COLUMN foo VARCHAR",
        "CREATE TABLE foo (id INT)",
    ]
    for stmt in forbidden:
        with pytest.raises(QueryValidationError, match="(?i)not allowed"):
            validate_query(conn, stmt)

    conn.close()


def test_execute_query_timeout(tmp_duckdb, monkeypatch):
    """Queries exceeding the timeout limit raise a TimeoutError."""
    original_submit = concurrent.futures.ThreadPoolExecutor.submit

    def mock_submit(self, fn, *args, **kwargs):
        future = original_submit(self, fn, *args, **kwargs)
        # Replace result() so it always raises TimeoutError
        future.result = lambda timeout=None: (_ for _ in ()).throw(
            concurrent.futures.TimeoutError()
        )
        return future

    monkeypatch.setattr(concurrent.futures.ThreadPoolExecutor, "submit", mock_submit)

    conn = connect_duckdb(tmp_duckdb)
    with pytest.raises(TimeoutError):
        execute_query(conn, "SELECT 1")
    conn.close()


# ---------------------------------------------------------------------------
# Row-limit tests
# ---------------------------------------------------------------------------


def test_apply_row_limit_adds_limit_when_missing():
    """apply_row_limit wraps SQL with LIMIT when no LIMIT clause is present."""
    sql = "SELECT * FROM cloudtrail_events"
    result = apply_row_limit(sql, 100)
    assert "LIMIT 100" in result.upper()
    assert "cloudtrail_events" in result


def test_apply_row_limit_preserves_existing_limit():
    """apply_row_limit returns SQL unchanged when a LIMIT clause already exists."""
    sql = "SELECT * FROM cloudtrail_events LIMIT 5"
    result = apply_row_limit(sql, 100)
    assert result == sql


def test_apply_row_limit_case_insensitive():
    """apply_row_limit detects lower-case 'limit' as well."""
    sql = "SELECT * FROM cloudtrail_events limit 10"
    result = apply_row_limit(sql, 500)
    assert result == sql


def test_apply_row_limit_strips_trailing_semicolon():
    """apply_row_limit strips a trailing semicolon before wrapping."""
    sql = "SELECT * FROM cloudtrail_events;"
    result = apply_row_limit(sql, 50)
    assert "LIMIT 50" in result.upper()
    # The wrapped SQL must not have a bare semicolon inside the subquery
    assert result.count(";") == 0


def test_execute_query_truncates_to_custom_row_limit(tmp_duckdb):
    """execute_query returns at most row_limit rows (custom limit < total rows)."""
    conn = connect_duckdb(tmp_duckdb)
    # The fixture has 3 rows; request at most 2
    df = execute_query(conn, "SELECT * FROM cloudtrail_events", row_limit=2)
    assert len(df) <= 2
    conn.close()


def test_execute_query_uses_default_row_limit(tmp_duckdb):
    """execute_query applies DEFAULT_ROW_LIMIT when row_limit is not specified."""
    conn = connect_duckdb(tmp_duckdb)
    df = execute_query(conn, "SELECT * FROM cloudtrail_events")
    assert len(df) <= DEFAULT_ROW_LIMIT
    conn.close()


def test_execute_query_respects_existing_sql_limit(tmp_duckdb):
    """execute_query does not override a LIMIT clause already in the SQL."""
    conn = connect_duckdb(tmp_duckdb)
    df = execute_query(conn, "SELECT * FROM cloudtrail_events LIMIT 1")
    assert len(df) == 1
    conn.close()


def test_execute_query_large_row_limit_returns_all_rows(tmp_duckdb):
    """execute_query returns all rows when row_limit exceeds the result size."""
    conn = connect_duckdb(tmp_duckdb)
    # Fixture has 3 rows; limit=100 should return all 3
    df = execute_query(conn, "SELECT * FROM cloudtrail_events", row_limit=100)
    assert len(df) == 3
    conn.close()

