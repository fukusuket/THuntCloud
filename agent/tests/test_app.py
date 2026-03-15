"""Tests for the Streamlit app entry point (app.py).

Test #22: session state initialization (Phase 6 of TDD plan).
Tests #23-#25: built-in hunt YAML structure and Direct SQL execution.
Tests #DF-A/B: date range filter session state and _handle_direct_sql integration.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd


def test_session_state_initialization():
    """Session state is populated with expected keys on startup.

    Test #22 — AGT-01/AGT-09: verifies that _init_session_state() creates
    all required keys in st.session_state when they are absent.
    """
    mock_state = {}
    with patch("streamlit.session_state", mock_state):
        from app import SESSION_STATE_DEFAULTS, _init_session_state

        _init_session_state()
        for key in SESSION_STATE_DEFAULTS:
            assert key in mock_state, f"Expected session state key '{key}' to be set"


def test_session_state_does_not_overwrite_existing_keys():
    """Existing session state keys must not be overwritten by _init_session_state().

    Ensures idempotent behavior when the page reloads mid-session.
    """
    existing_messages = [{"role": "user", "content": "hello"}]
    mock_state = {"messages": existing_messages}
    with patch("streamlit.session_state", mock_state):
        from app import _init_session_state

        _init_session_state()
        assert mock_state["messages"] == existing_messages


def test_session_state_messages_default_is_empty_list():
    """messages key must default to an empty list."""
    mock_state = {}
    with patch("streamlit.session_state", mock_state):
        from app import _init_session_state

        _init_session_state()
        assert mock_state["messages"] == []


def test_session_state_query_history_default_is_empty_list():
    """query_history key must default to an empty list."""
    mock_state = {}
    with patch("streamlit.session_state", mock_state):
        from app import _init_session_state

        _init_session_state()
        assert mock_state["query_history"] == []


def test_session_state_model_default():
    """model key must default to 'gpt-5.4'."""
    mock_state = {}
    with patch("streamlit.session_state", mock_state):
        from app import _init_session_state

        _init_session_state()
        assert mock_state["model"] == "gpt-5.4"


def test_load_builtin_prompts_returns_nonempty_list():
    """_load_builtin_prompts() must return a non-empty list of dicts with label/prompt keys."""
    from app import _load_builtin_prompts

    prompts = _load_builtin_prompts()
    assert isinstance(prompts, list)
    assert len(prompts) > 0
    for entry in prompts:
        assert "label" in entry, "Each prompt entry must have a 'label' key"
        assert "prompt" in entry, "Each prompt entry must have a 'prompt' key"


def test_load_builtin_prompts_includes_root_account():
    """Built-in prompts must include a root account activity entry."""
    from app import _load_builtin_prompts

    prompts = _load_builtin_prompts()
    labels = [p["label"] for p in prompts]
    assert any(
        "Root" in label for label in labels
    ), "Expected a 'Root Account' entry in built-in prompts"


def test_export_session_returns_valid_json():
    """_export_session() must return a JSON-serialisable string."""

    from app import _export_session
    from report import ReportEntry

    entries = [
        ReportEntry(
            sql="SELECT 1",
            results=pd.DataFrame({"a": [1]}),
        )
    ]
    result = _export_session(entries, title="Test Hunt")
    # Must be valid JSON
    parsed = json.loads(result)
    assert parsed["title"] == "Test Hunt"
    assert len(parsed["queries"]) == 1
    assert parsed["queries"][0]["sql"] == "SELECT 1"


def test_export_session_empty_entries():
    """_export_session() must handle an empty entry list gracefully."""
    from app import _export_session

    result = _export_session([], title="Empty Hunt")
    parsed = json.loads(result)
    assert parsed["queries"] == []


# ---------------------------------------------------------------------------
# Test #23 — builtin_hunts.yaml structure validation
# ---------------------------------------------------------------------------


def test_builtin_hunts_yaml_has_required_fields():
    """All entries in builtin_hunts.yaml must have category, label, description, prompt.

    Test #23: enforces the v2 schema after the built-in query enhancement.
    """
    from app import _load_builtin_prompts

    prompts = _load_builtin_prompts()
    assert len(prompts) > 0, "builtin_hunts.yaml must not be empty"
    for entry in prompts:
        label = entry.get("label", "<unknown>")
        assert "category" in entry, f"Missing 'category' in entry: {label!r}"
        assert "label" in entry, "Missing 'label' in entry"
        assert "description" in entry, f"Missing 'description' in entry: {label!r}"
        assert "prompt" in entry, f"Missing 'prompt' in entry: {label!r}"


def test_builtin_hunts_yaml_has_direct_sql_entries():
    """At least one entry must contain a 'sql' field for direct execution.

    Test #23b: verifies that the sql field enhancement was actually applied.
    """
    from app import _load_builtin_prompts

    prompts = _load_builtin_prompts()
    sql_entries = [p for p in prompts if p.get("sql")]
    assert (
        len(sql_entries) >= 10
    ), f"Expected at least 10 direct-SQL entries, got {len(sql_entries)}"


# ---------------------------------------------------------------------------
# Test #24 — Direct SQL entries must be valid DuckDB
# ---------------------------------------------------------------------------


def test_builtin_hunts_direct_sql_is_valid_duckdb(tmp_path):
    """Every 'sql' field in builtin_hunts.yaml must pass DuckDB EXPLAIN validation.

    Test #24: prevents broken SQL from shipping in built-in presets.
    Uses a temporary DB with the full cloudtrail_events schema.
    """
    from app import _load_builtin_prompts
    from query import validate_query

    db_path = str(tmp_path / "test.db")
    conn_rw = duckdb.connect(db_path)
    conn_rw.execute("""
        CREATE TABLE cloudtrail_events (
            event_time               TIMESTAMP,
            event_name               VARCHAR,
            event_source             VARCHAR,
            aws_region               VARCHAR,
            source_ip_address        VARCHAR,
            user_agent               VARCHAR,
            user_identity_type       VARCHAR,
            user_identity_arn        VARCHAR,
            user_identity_account_id VARCHAR,
            request_parameters       VARCHAR,
            response_elements        VARCHAR,
            error_code               VARCHAR,
            error_message            VARCHAR,
            read_only                BOOLEAN,
            event_type               VARCHAR,
            recipient_account_id     VARCHAR,
            raw_event                VARCHAR
        )
    """)
    conn_rw.close()

    conn_ro = duckdb.connect(db_path, read_only=True)
    try:
        prompts = _load_builtin_prompts()
        for entry in prompts:
            sql = entry.get("sql")
            if sql:
                validate_query(conn_ro, sql), (
                    f"SQL validation failed for preset {entry['label']!r}"
                )
    finally:
        conn_ro.close()


# ---------------------------------------------------------------------------
# Test #25 — _handle_direct_sql() works without an API key
# ---------------------------------------------------------------------------


def test_handle_direct_sql_no_api_key_shows_results(tmp_duckdb):
    """Direct SQL execution must succeed and populate session state without an API key.

    Test #25: verifies the _handle_direct_sql() path that bypasses OpenAI.
    """
    from tests.conftest import MockSessionState

    sql = (
        "SELECT event_time, event_name, aws_region "
        "FROM cloudtrail_events ORDER BY event_time DESC LIMIT 10"
    )

    mock_state = MockSessionState(
        api_key="",  # no API key
        model="gpt-5.4",
        messages=[],
        query_history=[],
        last_sql="",
        last_results=None,
        last_summary="",
        date_start=None,  # no date filter
        date_end=None,
    )

    with (
        patch("streamlit.session_state", mock_state),
        patch("streamlit.spinner") as mock_spinner,
        patch("streamlit.warning"),
    ):
        # spinner must work as a context manager
        mock_spinner.return_value.__enter__ = MagicMock(return_value=None)
        mock_spinner.return_value.__exit__ = MagicMock(return_value=False)

        from app import _handle_direct_sql

        _handle_direct_sql(sql, tmp_duckdb)

    # Results must be stored
    assert mock_state["last_sql"] == sql
    assert mock_state["last_results"] is not None
    assert len(mock_state["last_results"]) == 3  # 3 rows from conftest fixture
    # Without an API key, summary should be empty
    assert mock_state["last_summary"] == ""
    # One assistant message must be appended
    assert len(mock_state["messages"]) == 1
    assert mock_state["messages"][0]["role"] == "assistant"
    # Query history must be updated
    assert len(mock_state["query_history"]) == 1


# ---------------------------------------------------------------------------
# Tests #DF-A / #DF-B — Date range filter
# ---------------------------------------------------------------------------


def test_session_state_has_date_filter_defaults():
    """Session state must include date_start and date_end keys defaulting to None.

    Test #DF-A: verifies that _init_session_state() creates date filter keys.
    """
    mock_state = {}
    with patch("streamlit.session_state", mock_state):
        from app import _init_session_state

        _init_session_state()

    assert "date_start" in mock_state, "Expected 'date_start' key in session state"
    assert "date_end" in mock_state, "Expected 'date_end' key in session state"
    assert mock_state["date_start"] is None
    assert mock_state["date_end"] is None


# ---------------------------------------------------------------------------
# Tests #AI-A / #AI-B / #AI-C — _analyze_current_results()
# ---------------------------------------------------------------------------


def test_analyze_current_results_sets_last_summary_without_appending_message():
    """_analyze_current_results() must store the analysis in last_summary only.

    Test #AI-A: The analysis result is displayed below the results table via
    last_summary, NOT appended to the chat message history.
    """
    from tests.conftest import MockSessionState

    results_df = pd.DataFrame(
        {"event_name": ["ConsoleLogin"], "aws_region": ["us-east-1"]}
    )
    mock_state = MockSessionState(
        api_key="sk-test",
        model="gpt-5.4",
        messages=[],
        query_history=[],
        last_sql="SELECT event_name, aws_region FROM cloudtrail_events",
        last_results=results_df,
        last_summary="",
        date_start=None,
        date_end=None,
    )

    with (
        patch("streamlit.session_state", mock_state),
        patch("streamlit.spinner") as mock_spinner,
        patch("llm.OpenAI") as mock_openai_cls,
    ):
        mock_spinner.return_value.__enter__ = MagicMock(return_value=None)
        mock_spinner.return_value.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "• 1 ConsoleLogin event observed"
        mock_client.chat.completions.create.return_value = mock_response

        from app import _analyze_current_results

        _analyze_current_results()

    assert mock_state["last_summary"] == "• 1 ConsoleLogin event observed"
    # Analysis must NOT be added to the chat message history
    assert len(mock_state["messages"]) == 0


def test_analyze_current_results_no_api_key_appends_warning():
    """_analyze_current_results() must append a warning when no API key is set.

    Test #AI-B: verifies early-return behavior without an API key.
    generate_analysis must NOT be called.
    """
    from tests.conftest import MockSessionState

    mock_state = MockSessionState(
        api_key="",
        model="gpt-5.4",
        messages=[],
        query_history=[],
        last_sql="SELECT 1",
        last_results=pd.DataFrame({"a": [1]}),
        last_summary="",
        date_start=None,
        date_end=None,
    )

    with (
        patch("streamlit.session_state", mock_state),
        patch("llm.OpenAI") as mock_openai_cls,
    ):
        from app import _analyze_current_results

        _analyze_current_results()

    mock_openai_cls.assert_not_called()
    assert len(mock_state["messages"]) == 1
    assert "API key" in mock_state["messages"][0]["content"]


def test_analyze_current_results_no_results_does_nothing():
    """_analyze_current_results() must be a no-op when last_results is None.

    Test #AI-C: verifies that nothing is appended when there are no results to analyse.
    """
    from tests.conftest import MockSessionState

    mock_state = MockSessionState(
        api_key="sk-test",
        model="gpt-5.4",
        messages=[],
        query_history=[],
        last_sql="",
        last_results=None,
        last_summary="",
        date_start=None,
        date_end=None,
    )

    with (
        patch("streamlit.session_state", mock_state),
        patch("llm.OpenAI") as mock_openai_cls,
    ):
        from app import _analyze_current_results

        _analyze_current_results()

    mock_openai_cls.assert_not_called()
    assert len(mock_state["messages"]) == 0


def test_handle_direct_sql_applies_date_filter_from_session_state(tmp_duckdb):
    """_handle_direct_sql stores date-filtered SQL when date_start/date_end are set.

    Test #DF-B: verifies that apply_date_filter is applied inside _handle_direct_sql
    when date_start and date_end are present in session state.
    """
    from tests.conftest import MockSessionState

    sql = "SELECT * FROM cloudtrail_events LIMIT 10"

    mock_state = MockSessionState(
        api_key="",
        model="gpt-5.4",
        messages=[],
        query_history=[],
        last_sql="",
        last_results=None,
        last_summary="",
        date_start=date(2024, 1, 1),
        date_end=date(2024, 12, 31),
    )

    with (
        patch("streamlit.session_state", mock_state),
        patch("streamlit.spinner") as mock_spinner,
        patch("streamlit.warning"),
    ):
        mock_spinner.return_value.__enter__ = MagicMock(return_value=None)
        mock_spinner.return_value.__exit__ = MagicMock(return_value=False)

        from app import _handle_direct_sql

        _handle_direct_sql(sql, tmp_duckdb)

    # The stored SQL must include the date filter CTE
    assert (
        "_ct_filtered" in mock_state["last_sql"]
    ), "Expected '_ct_filtered' CTE in last_sql when date filter is active"
    assert "2024-01-01" in mock_state["last_sql"]
    assert "2024-12-31" in mock_state["last_sql"]
    # All 3 rows must be returned (all are within 2024)
    assert mock_state["last_results"] is not None
    assert len(mock_state["last_results"]) == 3
