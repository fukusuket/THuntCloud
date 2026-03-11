"""Streamlit entry point for the THuntCloud AI threat hunting agent.

Provides an interactive chat UI for AI-assisted threat hunting on
AWS CloudTrail logs stored in DuckDB.
"""

import json
import logging
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from llm import generate_analysis, generate_sql
from query import QueryValidationError, connect_duckdb, execute_query
from report import ReportEntry, generate_report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to the built-in threat hunting prompts YAML file.
_BUILTIN_PROMPTS_PATH = Path(__file__).parent / "builtin_hunts.yaml"

# Session state keys and their default values.
SESSION_STATE_DEFAULTS: dict = {
    "messages": [],  # chat history: list of {role, content}
    "query_history": [],  # list of ReportEntry for report generation
    "last_sql": "",  # most recently generated SQL (editable)
    "last_results": None,  # pandas DataFrame or None
    "last_analysis": "",  # AI analysis text
    "api_key": "",  # entered in sidebar (AGT-09)
    "model": "gpt-5.4",  # selected model
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _init_session_state() -> None:
    """Initialize Streamlit session state with default values.

    Idempotent: only sets keys that are not already present, so existing
    session data is never overwritten on page reload.
    """
    for key, default in SESSION_STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def _load_builtin_prompts() -> list[dict]:
    """Load built-in threat hunting prompts from the YAML file.

    Returns:
        A list of dicts, each containing 'label' and 'prompt' keys.
        Falls back to a minimal built-in list if the file is not found.
    """
    try:
        with open(_BUILTIN_PROMPTS_PATH, encoding="utf-8") as f:
            prompts = yaml.safe_load(f)
        if isinstance(prompts, list):
            return prompts
    except FileNotFoundError:
        logger.warning("builtin_hunts.yaml not found at %s", _BUILTIN_PROMPTS_PATH)
    except yaml.YAMLError as exc:
        logger.error("Failed to parse builtin_hunts.yaml: %s", exc)

    # Fallback minimal list
    return [
        {
            "label": "🔑 Root Account Activity",
            "prompt": (
                "List all API calls made by the root account. Include event_time, "
                "event_name, source_ip_address, and aws_region. Order by most recent first."
            ),
        },
        {
            "label": "🚫 Access Denied Errors",
            "prompt": (
                "Show all AccessDenied and UnauthorizedAccess errors in the logs. "
                "Group by user identity and event_name to find the top offenders."
            ),
        },
    ]


def _export_session(
    entries: list[ReportEntry], title: str = "Threat Hunting Session"
) -> str:
    """Export the current session as a JSON string.

    Serialises all ReportEntry objects to a JSON payload for download
    or later re-import (AGT-08).

    Args:
        entries: List of ReportEntry objects from the current session.
        title:   Human-readable session title.

    Returns:
        A JSON-formatted string representing the session.
    """
    queries = [
        {
            "sql": entry.sql,
            "analysis": entry.analysis,
            "row_count": len(entry.results) if entry.results is not None else 0,
        }
        for entry in entries
    ]
    payload = {
        "title": title,
        "queries": queries,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# UI rendering
# ---------------------------------------------------------------------------


def _get_duckdb_path() -> str:
    """Resolve the DuckDB path from environment variable."""
    return os.environ.get("DUCKDB_PATH", "/data/db/threat_hunting.db")


def render_sidebar() -> None:
    """Render the sidebar: API key, model selection, presets, report, session export.

    Handles AGT-07 (preset prompts), AGT-08 (session export), AGT-09 (API key).
    """
    with st.sidebar:
        st.title("⚙️ Settings")

        # AGT-09: API key input
        st.subheader("🔑 API Configuration")
        api_key_input = st.text_input(
            "OpenAI API Key",
            value=st.session_state.api_key,
            type="password",
            help="Your OpenAI API key. Never stored outside this browser session.",
        )
        if api_key_input != st.session_state.api_key:
            st.session_state.api_key = api_key_input

        # Model selection
        model_options = ["gpt-5.4", "gpt-5.4-mini"]
        selected_model = st.selectbox(
            "Model",
            options=model_options,
            index=(
                model_options.index(st.session_state.model)
                if st.session_state.model in model_options
                else 0
            ),
        )
        if selected_model != st.session_state.model:
            st.session_state.model = selected_model

        st.divider()

        # AGT-07: Preset threat hunting prompts
        st.subheader("🎯 Preset Hunt Queries")
        prompts = _load_builtin_prompts()
        preset_labels = ["— Select a preset —"] + [p["label"] for p in prompts]
        selected_label = st.selectbox("Presets", options=preset_labels)
        if selected_label != "— Select a preset —":
            matched = next((p for p in prompts if p["label"] == selected_label), None)
            if matched:
                if st.button("▶ Use This Preset", use_container_width=True):
                    st.session_state["_pending_preset"] = matched["prompt"].strip()
                    st.rerun()

        st.divider()

        # AGT-06: Markdown report download
        st.subheader("📄 Report")
        if st.session_state.query_history:
            report_md = generate_report(
                st.session_state.query_history,
                title="THuntCloud Threat Hunting Report",
            )
            st.download_button(
                label="⬇ Download Markdown Report",
                data=report_md,
                file_name="threat_hunting_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        else:
            st.caption("Run at least one query to generate a report.")

        st.divider()

        # AGT-08: Session export
        st.subheader("💾 Session")
        col1, col2 = st.columns(2)
        with col1:
            if st.session_state.query_history:
                session_json = _export_session(
                    st.session_state.query_history,
                    title="THuntCloud Session",
                )
                st.download_button(
                    label="Export JSON",
                    data=session_json,
                    file_name="session.json",
                    mime="application/json",
                    use_container_width=True,
                )
            else:
                st.button("Export JSON", disabled=True, use_container_width=True)

        with col2:
            if st.button("🗑 Clear", use_container_width=True):
                st.session_state.messages = []
                st.session_state.query_history = []
                st.session_state.last_sql = ""
                st.session_state.last_results = None
                st.session_state.last_analysis = ""
                st.rerun()


def _handle_user_query(user_input: str, db_path: str) -> None:
    """Process a user query: generate SQL, execute, analyse, and update state.

    Implements the full AGT-01 → AGT-02 → AGT-03 → AGT-04 → AGT-05 pipeline.

    Args:
        user_input: The natural language question from the user.
        db_path:    Path to the DuckDB database file.
    """
    api_key = st.session_state.api_key
    model = st.session_state.model

    if not api_key:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "⚠️ Please enter your OpenAI API key in the sidebar first.",
            }
        )
        return

    # Step 1: Generate SQL (AGT-02)
    with st.spinner("🤖 Generating SQL…"):
        sql = generate_sql(user_input, api_key=api_key, model=model)

    st.session_state.last_sql = sql

    # Step 2: Execute query (AGT-03/04)
    results = pd.DataFrame()
    error_message: str | None = None
    try:
        conn = connect_duckdb(db_path)
        results = execute_query(conn, sql)
        conn.close()
    except QueryValidationError as exc:
        error_message = f"🚫 SQL validation error: {exc}"
    except TimeoutError:
        error_message = "⏱ Query timed out (30 s limit exceeded)."
    except Exception as exc:  # noqa: BLE001
        error_message = f"❌ Query execution error: {exc}"

    st.session_state.last_results = results if error_message is None else None

    # Step 3: Generate analysis (AGT-05)
    analysis = ""
    if error_message is None:
        with st.spinner("📊 Analysing results…"):
            analysis = generate_analysis(sql, results, api_key=api_key, model=model)
    st.session_state.last_analysis = analysis

    # Step 4: Append to chat history and query history
    if error_message:
        assistant_content = error_message
    else:
        assistant_content = (
            f"**Generated SQL:**\n```sql\n{sql}\n```\n\n"
            f"**Results:** {len(results)} row(s)\n\n"
            f"**Analysis:**\n{analysis}"
        )

    st.session_state.messages.append(
        {"role": "assistant", "content": assistant_content}
    )

    if error_message is None:
        st.session_state.query_history.append(
            ReportEntry(sql=sql, results=results, analysis=analysis)
        )


def render_chat() -> None:
    """Render the main chat area.

    Displays chat history (AGT-01), SQL editor (AGT-03), results table (AGT-04),
    and AI analysis (AGT-05).
    """
    st.header("🔍 THuntCloud — AI Threat Hunting Agent")
    st.caption("Ask natural language questions about your CloudTrail logs.")

    db_path = _get_duckdb_path()

    # Handle any pending preset injected from the sidebar
    pending_preset = st.session_state.pop("_pending_preset", None)

    # ---- Chat history ----
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ---- SQL editor for the last query (AGT-03) ----
    if st.session_state.last_sql:
        with st.expander("🛠 Edit & Re-run SQL", expanded=False):
            edited_sql = st.text_area(
                "SQL",
                value=st.session_state.last_sql,
                height=150,
                label_visibility="collapsed",
            )
            if st.button("▶ Run Edited SQL"):
                api_key = st.session_state.api_key
                if not api_key:
                    st.warning("Enter your API key in the sidebar first.")
                else:
                    try:
                        conn = connect_duckdb(db_path)
                        results = execute_query(conn, edited_sql)
                        conn.close()
                        st.session_state.last_sql = edited_sql
                        st.session_state.last_results = results

                        with st.spinner("📊 Analysing results…"):
                            analysis = generate_analysis(
                                edited_sql,
                                results,
                                api_key=api_key,
                                model=st.session_state.model,
                            )
                        st.session_state.last_analysis = analysis
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    f"**Re-run SQL:**\n```sql\n{edited_sql}\n```\n\n"
                                    f"**Results:** {len(results)} row(s)\n\n"
                                    f"**Analysis:**\n{analysis}"
                                ),
                            }
                        )
                        st.session_state.query_history.append(
                            ReportEntry(
                                sql=edited_sql, results=results, analysis=analysis
                            )
                        )
                        st.rerun()
                    except (
                        QueryValidationError,
                        TimeoutError,
                        Exception,
                    ) as exc:  # noqa: BLE001
                        st.error(f"Error: {exc}")

    # ---- Latest results table (AGT-04) ----
    if (
        st.session_state.last_results is not None
        and not st.session_state.last_results.empty
    ):
        with st.expander("📋 Latest Query Results", expanded=True):
            st.dataframe(st.session_state.last_results, use_container_width=True)

    # ---- Chat input (AGT-01) ----
    user_input = st.chat_input("Ask a threat hunting question…") or pending_preset

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        _handle_user_query(user_input, db_path)
        st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Configure and render the Streamlit application."""
    st.set_page_config(
        page_title="THuntCloud",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_session_state()
    render_sidebar()
    render_chat()


if __name__ == "__main__":
    main()
