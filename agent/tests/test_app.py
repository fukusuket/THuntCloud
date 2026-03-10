"""Tests for the Streamlit app entry point (app.py).

Test #22: session state initialization (Phase 6 of TDD plan).
"""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


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
    assert any("Root" in label for label in labels), (
        "Expected a 'Root Account' entry in built-in prompts"
    )


def test_export_session_returns_valid_json():
    """_export_session() must return a JSON-serialisable string."""
    import pandas as pd

    from app import _export_session
    from report import ReportEntry

    entries = [
        ReportEntry(
            sql="SELECT 1",
            results=pd.DataFrame({"a": [1]}),
            analysis="test analysis",
        )
    ]
    result = _export_session(entries, title="Test Hunt")
    # Must be valid JSON
    parsed = json.loads(result)
    assert parsed["title"] == "Test Hunt"
    assert len(parsed["queries"]) == 1
    assert parsed["queries"][0]["sql"] == "SELECT 1"
    assert parsed["queries"][0]["analysis"] == "test analysis"


def test_export_session_empty_entries():
    """_export_session() must handle an empty entry list gracefully."""
    from app import _export_session

    result = _export_session([], title="Empty Hunt")
    parsed = json.loads(result)
    assert parsed["queries"] == []

