"""Tests for query.py — DuckDB query execution and validation."""

import concurrent.futures

import pandas as pd
import pytest

from query import QueryValidationError, connect_duckdb, execute_query, validate_query


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
