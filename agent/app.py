"""Streamlit entry point for the THuntCloud AI threat hunting agent.

Provides an interactive chat UI for AI-assisted threat hunting on
AWS CloudTrail logs stored in DuckDB.
"""

import json
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from llm import MAX_CONTEXT_TURNS, generate_analysis, generate_sql
from query import (
    DEFAULT_ROW_LIMIT,
    QueryValidationError,
    apply_date_filter,
    connect_duckdb,
    execute_query,
    execute_with_retry,
)
from report import ReportEntry, generate_report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to the built-in threat hunting prompts YAML file.
_BUILTIN_PROMPTS_PATH = Path(__file__).parent / "builtin_hunts.yaml"

# Info banner shown in the chat area when no API key is configured.
_NO_API_KEY_BANNER = (
    "💡 **No API key needed for preset queries.** "
    "Select a category in the sidebar and click **⚡ Direct SQL** to run "
    "pre-built threat hunting queries instantly."
)

# Session state keys and their default values.
SESSION_STATE_DEFAULTS: dict = {
    "messages": [],  # chat history: list of {role, content}
    "query_history": [],  # list of ReportEntry for report generation
    "last_sql": "",  # most recently generated SQL (editable)
    "last_results": None,  # pandas DataFrame or None
    "last_summary": "",  # fact-based summary from the last query
    "api_key": "",  # entered in sidebar (AGT-09)
    "model": "gpt-5.4",  # selected model
    "date_start": None,  # date | None — lower bound for event_time filter
    "date_end": None,  # date | None — upper bound for event_time filter
    "conversation_context": [],  # recent (user_query, sql, summary) turns for LLM context
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
        # Date range filter
        st.subheader("📅 Date Range Filter")
        today = date.today()
        # Manual date inputs
        dc1, dc2 = st.columns(2)
        with dc1:
            new_start = st.date_input(
                "From",
                value=st.session_state.date_start,
                max_value=today,
                format="YYYY-MM-DD",
                key="_date_start_input",
            )
        with dc2:
            new_end = st.date_input(
                "To",
                value=st.session_state.date_end,
                max_value=today,
                format="YYYY-MM-DD",
                key="_date_end_input",
            )

        # Persist date selections
        st.session_state.date_start = new_start or None
        st.session_state.date_end = new_end or None

        if new_start and new_end and new_start > new_end:
            st.error("⚠️ 'From' date must be before or equal to 'To' date.")
        elif new_start or new_end:
            start_s = str(new_start) if new_start else "—"
            end_s = str(new_end) if new_end else "—"
            st.caption(f"🔍 Active filter: **{start_s}** → **{end_s}**")

        # AGT-07: Preset threat hunting prompts (v2 — category grouping + Direct SQL)
        st.subheader("🎯 Preset Hunt Queries")
        prompts = _load_builtin_prompts()

        # Build category list preserving insertion order
        categories: list[str] = []
        seen_cats: set[str] = set()
        for p in prompts:
            cat = p.get("category", "Other")
            if cat not in seen_cats:
                categories.append(cat)
                seen_cats.add(cat)

        selected_category = st.selectbox(
            "Category",
            options=["— All categories —"] + categories,
            key="_preset_category",
        )

        # Filter prompts by selected category
        if selected_category == "— All categories —":
            filtered = prompts
        else:
            filtered = [p for p in prompts if p.get("category") == selected_category]

        preset_labels = ["— Select a preset —"] + [p["label"] for p in filtered]
        selected_label = st.selectbox(
            "Preset",
            options=preset_labels,
            key="_preset_label",
        )

        if selected_label != "— Select a preset —":
            matched = next((p for p in filtered if p["label"] == selected_label), None)
            if matched:
                # Show description when available
                desc = matched.get("description", "")
                if desc:
                    st.caption(f"ℹ️ {desc}")

                has_sql = bool(matched.get("sql", "").strip())

                if has_sql:
                    if st.button(
                        "⚡ Direct SQL",
                        use_container_width=True,
                        help="Run without an API key",
                    ):
                        st.session_state["_pending_direct_sql"] = matched["sql"].strip()
                        st.rerun()
                else:
                    st.button(
                        "⚡ Direct SQL",
                        disabled=True,
                        use_container_width=True,
                        help="No pre-built SQL for this preset",
                    )

        st.divider()

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
                st.session_state.last_summary = ""
                st.session_state.conversation_context = []
                st.rerun()


def _handle_direct_sql(sql: str, db_path: str) -> None:
    """Execute a pre-built SQL query directly without requiring an API key.

    Runs the SQL against the DuckDB database in read-only mode, stores results
    in session state, and appends a message to the chat history.  An optional
    AI summary is generated when an API key is present.

    Args:
        sql:     Validated DuckDB SQL from a built-in preset entry.
        db_path: Path to the DuckDB database file.
    """
    # Apply date range filter (wraps sql in a date-scoped CTE when active).
    sql = apply_date_filter(sql, st.session_state.date_start, st.session_state.date_end)

    results = pd.DataFrame()
    error_message: str | None = None

    with st.spinner("⚡ Running direct SQL…"):
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

    st.session_state.last_sql = sql
    st.session_state.last_results = results if error_message is None else None
    st.session_state.last_summary = ""

    # Build assistant message
    if error_message:
        assistant_content = error_message
    else:
        truncated = len(results) >= DEFAULT_ROW_LIMIT
        row_info = f"{len(results)} row(s)" + (
            f" _(truncated to {DEFAULT_ROW_LIMIT:,})_" if truncated else ""
        )
        assistant_content = (
            f"**Direct SQL query executed:**\n```sql\n{sql}\n```\n\n"
            f"**Results:** {row_info}"
        )

    st.session_state.messages.append(
        {"role": "assistant", "content": assistant_content}
    )

    if error_message is None:
        st.session_state.query_history.append(
            ReportEntry(sql=sql, results=results, analysis="")
        )


def _analyze_current_results() -> None:
    """Analyze the current query results using AI and append the analysis to chat.

    Calls generate_analysis() with last_sql and last_results already stored in
    session state.  Requires an API key; appends a warning message when none is
    set.  Does nothing when last_results is None or empty.
    """
    api_key = st.session_state.api_key
    model = st.session_state.model
    sql = st.session_state.last_sql
    results = st.session_state.last_results

    if not api_key:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "⚠️ Please enter your OpenAI API key in the sidebar first.",
            }
        )
        return

    if results is None or (hasattr(results, "empty") and results.empty):
        return

    with st.spinner("🤖 Analyzing results…"):
        summary = generate_analysis(sql, results, api_key=api_key, model=model)

    st.session_state.last_summary = summary

    # Persist analysis into the last query_history entry so the history view
    # can display it without requiring a separate state variable.
    if st.session_state.query_history and summary:
        st.session_state.query_history[-1].analysis = summary


def _handle_user_query(user_input: str, db_path: str) -> None:
    """Process a user query: generate SQL, execute, summarise, and update state.

    Implements the AGT-01 → AGT-02 → AGT-03 → AGT-04 → AGT-05 pipeline.
    The summary step (AGT-05) produces only fact-based bullet points;
    speculative threat assessments are excluded by the LLM prompt.

    Conversation context from previous turns is forwarded to generate_sql()
    so that follow-up questions such as "drill down on that" work naturally.

    If the generated SQL fails validation, execute_with_retry() asks the LLM
    to correct it (up to 2 attempts) before surfacing the error to the user.

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

    # Step 1: Generate SQL (AGT-02), injecting prior conversation context.
    # Take a snapshot so that the context passed to the LLM is not mutated
    # by the append at the end of this function.
    context = list(st.session_state.conversation_context)
    with st.spinner("🤖 Generating SQL…"):
        sql = generate_sql(user_input, api_key=api_key, model=model, context=context)

    # Apply date range filter to the AI-generated SQL (wraps in CTE when active).
    sql = apply_date_filter(sql, st.session_state.date_start, st.session_state.date_end)

    original_sql = sql  # preserve to detect LLM corrections later
    final_sql = sql
    st.session_state.last_sql = sql

    # Step 2: Execute query with automatic SQL correction on validation failure (AGT-03/04).
    results = pd.DataFrame()
    error_message: str | None = None
    try:
        conn = connect_duckdb(db_path)
        results, final_sql = execute_with_retry(
            conn, sql, api_key=api_key, model=model
        )
        conn.close()
        if final_sql != original_sql:
            sql = final_sql
            st.session_state.last_sql = sql
    except QueryValidationError as exc:
        error_message = f"🚫 SQL validation error: {exc}"
    except TimeoutError:
        error_message = "⏱ Query timed out (30 s limit exceeded)."
    except Exception as exc:  # noqa: BLE001
        error_message = f"❌ Query execution error: {exc}"

    st.session_state.last_results = results if error_message is None else None

    # Step 3: Generate fact-based summary (AGT-05)
    summary = ""
    if error_message is None:
        with st.spinner("📋 Summarising results…"):
            summary = generate_analysis(sql, results, api_key=api_key, model=model)
    st.session_state.last_summary = summary

    # Step 4: Append to chat history and query history.
    if error_message:
        assistant_content = error_message
    else:
        truncated = len(results) >= DEFAULT_ROW_LIMIT
        row_summary = f"{len(results)} row(s)" + (
            f" _(truncated to {DEFAULT_ROW_LIMIT:,} — add LIMIT to your SQL for more control)_"
            if truncated
            else ""
        )
        retry_notice = (
            "\n\n⚠️ _SQL was auto-corrected by the AI assistant._"
            if final_sql != original_sql
            else ""
        )
        assistant_content = (
            f"**Generated SQL:**\n```sql\n{sql}\n```\n\n"
            f"**Results:** {row_summary}\n\n"
            f"**Summary:**\n{summary}"
            + retry_notice
        )

    st.session_state.messages.append(
        {"role": "assistant", "content": assistant_content}
    )

    if error_message is None:
        st.session_state.query_history.append(
            ReportEntry(sql=sql, results=results, analysis=summary)
        )
        # Update conversation context for follow-up queries.
        summary_text = summary if summary else "(no summary)"
        st.session_state.conversation_context.append(
            {"user_query": user_input, "sql": sql, "summary": summary_text}
        )
        # Keep only the most recent MAX_CONTEXT_TURNS entries.
        if len(st.session_state.conversation_context) > MAX_CONTEXT_TURNS:
            st.session_state.conversation_context = (
                st.session_state.conversation_context[-MAX_CONTEXT_TURNS:]
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

    # Handle direct SQL execution from a built-in preset (no AI needed)
    pending_direct_sql = st.session_state.pop("_pending_direct_sql", None)
    if pending_direct_sql:
        _handle_direct_sql(pending_direct_sql, db_path)
        st.rerun()

    # Handle AI analysis request triggered from the results area
    pending_ai_analysis = st.session_state.pop("_pending_ai_analysis", None)
    if pending_ai_analysis:
        _analyze_current_results()
        st.rerun()

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

                        row_count = len(results)
                        truncated = row_count >= DEFAULT_ROW_LIMIT

                        with st.spinner("📋 Summarising results…"):
                            summary = generate_analysis(
                                edited_sql,
                                results,
                                api_key=api_key,
                                model=st.session_state.model,
                            )
                        st.session_state.last_summary = summary
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    f"**Re-run SQL:**\n```sql\n{edited_sql}\n```\n\n"
                                    f"**Results:** {row_count} row(s)"
                                    + (
                                        f" _(truncated to {DEFAULT_ROW_LIMIT:,} — add LIMIT to your SQL for more control)_"
                                        if truncated
                                        else ""
                                    )
                                    + f"\n\n**Summary:**\n{summary}"
                                ),
                            }
                        )
                        # Summary is in the message above; clear so it does not
                        # also appear in the dedicated analysis section.
                        st.session_state.last_summary = ""
                        st.session_state.query_history.append(
                            ReportEntry(
                                sql=edited_sql, results=results, analysis=summary
                            )
                        )
                        st.rerun()
                    except (
                        QueryValidationError,
                        TimeoutError,
                        Exception,
                    ) as exc:  # noqa: BLE001
                        st.error(f"Error: {exc}")

    # ---- Query results history (all entries accumulated, AGT-04) ----
    # Every executed query is appended here; nothing is overwritten.
    if st.session_state.query_history:
        st.markdown("---")
        st.subheader("📊 Query Results History")

        for i, entry in enumerate(st.session_state.query_history, start=1):
            is_last = i == len(st.session_state.query_history)
            with st.expander(f"Query #{i}", expanded=True):
                st.code(entry.sql, language="sql")

                if entry.results is not None and not entry.results.empty:
                    if len(entry.results) >= DEFAULT_ROW_LIMIT:
                        st.warning(
                            f"⚠️ Results are truncated to **{DEFAULT_ROW_LIMIT:,} rows**. "
                            "Add a `LIMIT` clause or narrow your query for more specific results."
                        )
                    st.dataframe(entry.results, use_container_width=True)
                else:
                    st.info("No results returned.")

                if entry.analysis:
                    st.markdown("#### 🤖 AI Analysis")
                    st.info(entry.analysis)
                elif is_last:
                    # Show "Ask AI" button only for the latest entry that lacks analysis
                    st.divider()
                    has_api_key = bool(st.session_state.api_key)
                    if st.button(
                        "🤖 Ask AI — Analyze These Results",
                        key="analyze_last_btn",
                        use_container_width=True,
                        disabled=not has_api_key,
                        help=(
                            "Generate an AI analysis of the query results above."
                            if has_api_key
                            else "Enter your OpenAI API key in the sidebar to enable AI analysis."
                        ),
                    ):
                        st.session_state["_pending_ai_analysis"] = True
                        st.rerun()

    # ---- No API key guidance banner (Proposal 3) ----
    if not st.session_state.api_key:
        st.info(_NO_API_KEY_BANNER)

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
