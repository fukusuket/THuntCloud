# Agent Module — Implementation Plan

> Based on PRD.md Section 6.2 and agent/AGENTS.md.
> All code comments, documentation, and commit messages MUST be written in English.
> This document is the source of truth for the agent module implementation schedule.

---

## Overview

The agent module provides an interactive Streamlit UI for AI-assisted threat hunting on AWS CloudTrail logs stored in DuckDB. Users type natural language questions; the AI generates DuckDB SQL, executes it, and delivers analysis. The module also generates structured threat hunting reports (Markdown / PDF).

**DuckDB is always opened in `READ_ONLY` mode in this module.**

### Technology Stack

| Item              | Value                                          |
| ----------------- | ---------------------------------------------- |
| Language          | Python 3.12+                                   |
| Framework         | Streamlit ≥ 1.40                               |
| AI Integration    | OpenAI API (`gpt-5.4` default — see PRD §11.2) |
| DB Client         | `duckdb` Python package ≥ 1.2                  |
| Data Processing   | `pandas` ≥ 2.2                                 |
| Test Framework    | `pytest`, `pytest-mock`                        |
| Linter / Formatter| `ruff`, `black`                                |

### Module Structure

```
agent/
├── app.py                 # Streamlit entry point
├── llm.py                 # OpenAI API integration
├── query.py               # DuckDB query execution & validation
├── report.py              # Threat hunting report generation (Markdown/PDF)
├── schema.py              # CloudTrail table schema definitions
├── config.py              # Configuration management (env vars, settings)
├── prompts/
│   └── system_prompt.py   # System prompt templates for SQL generation
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Dev/test dependencies
├── Dockerfile
├── tests/
│   ├── conftest.py        # Shared fixtures (mock_openai_client, tmp_duckdb)
│   ├── test_config.py
│   ├── test_schema.py
│   ├── test_query.py
│   ├── test_llm.py
│   └── test_report.py
└── AGENTS.md
```

### TDD Overview — 22 Tests across 6 Phases

| Phase | Module        | Tests | Estimated Time |
| ----- | ------------- | ----- | -------------- |
| 0     | Setup         | —     | 0.5 h          |
| 1     | `config.py`   | #1–3  | 1 h            |
| 2     | `schema.py`   | #4–5  | 1 h            |
| 3     | `query.py`    | #6–11 | 2 h            |
| 4     | `llm.py`      | #12–17| 2 h            |
| 5     | `report.py`   | #18–21| 1.5 h          |
| 6     | `app.py`      | #22   | 1.5 h          |
| **Total** |           | **22**| **~9.5 h**     |

---

## Phase 0 — Environment Setup (Estimated: 0.5 h)

**Goal**: Create the project skeleton so that `pytest` and `ruff` can be invoked without errors.

### Tasks

1. Create `agent/requirements.txt` with runtime dependencies.
2. Create `agent/requirements-dev.txt` with dev/test dependencies.
3. Create `agent/prompts/__init__.py` (empty) so the package is importable.
4. Create `agent/prompts/system_prompt.py` with the `SYSTEM_PROMPT` template constant.
5. Create `agent/tests/conftest.py` with shared fixtures (`mock_openai_client`, `tmp_duckdb`).
6. Create stub files (`config.py`, `schema.py`, `query.py`, `llm.py`, `report.py`) — each containing only module-level docstrings.
7. Create `agent/Dockerfile` (see below).
8. Verify `pytest --collect-only` discovers 0 tests without errors.

### requirements.txt

```
streamlit>=1.40.0
openai>=1.60.0
duckdb>=1.2.0
pandas>=2.2.0
```

### requirements-dev.txt

```
pytest>=8.0.0
pytest-mock>=3.14.0
ruff>=0.9.0
black>=24.0.0
```

### conftest.py (tests/conftest.py)

```python
"""Shared pytest fixtures for the agent test suite."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client that returns a predefined SQL response."""
    with patch("agent.llm.OpenAI") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = (
            "SELECT event_name, COUNT(*) as cnt "
            "FROM cloudtrail_events "
            "GROUP BY event_name ORDER BY cnt DESC LIMIT 10"
        )
        client.chat.completions.create.return_value = response

        yield client


@pytest.fixture
def tmp_duckdb(tmp_path):
    """Create a temporary DuckDB with cloudtrail_events table and sample rows."""
    import duckdb

    db_path = tmp_path / "test.db"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
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
            request_parameters       JSON,
            response_elements        JSON,
            error_code               VARCHAR,
            error_message            VARCHAR,
            read_only                BOOLEAN,
            event_type               VARCHAR,
            recipient_account_id     VARCHAR,
            raw_event                JSON
        )
    """)
    conn.execute("""
        INSERT INTO cloudtrail_events (event_time, event_name, event_source, aws_region)
        VALUES
            ('2024-01-15 10:30:00', 'DescribeInstances', 'ec2.amazonaws.com', 'us-east-1'),
            ('2024-01-15 10:31:00', 'DescribeInstances', 'ec2.amazonaws.com', 'us-east-1'),
            ('2024-01-15 10:32:00', 'CreateUser',        'iam.amazonaws.com', 'us-east-1')
    """)
    conn.close()
    yield str(db_path)
```

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Deliverables

- `agent/requirements.txt`
- `agent/requirements-dev.txt`
- `agent/Dockerfile`
- `agent/prompts/__init__.py`
- `agent/prompts/system_prompt.py` (stub with `SYSTEM_PROMPT` constant)
- `agent/config.py` (stub)
- `agent/schema.py` (stub)
- `agent/query.py` (stub)
- `agent/llm.py` (stub)
- `agent/report.py` (stub)
- `agent/tests/__init__.py` (empty)
- `agent/tests/conftest.py`

---

## Phase 1 — `config.py` (Estimated: 1 h)

**Goal**: Make tests #1–3 green. Implement an `AppConfig` class that loads settings from environment variables with validation.

### TDD Cycle

| # | Test Name | Red: What fails | Green: Minimum implementation | Refactor |
|---|---|---|---|---|
| 1 | `test_config_reads_duckdb_path_from_env` | `AttributeError`: `AppConfig` undefined | Define `AppConfig` dataclass; read `DUCKDB_PATH` from `os.environ` | Extract `_require_env()` helper |
| 2 | `test_config_default_model_is_gpt_5_4` | `AssertionError`: attribute missing | Add `model: str = os.getenv("OPENAI_MODEL", "gpt-5.4")` field | Consolidate defaults in one place |
| 3 | `test_config_rejects_empty_api_key` | No error raised | Add validation in `__post_init__` that raises `ValueError` when `api_key` is empty | Add descriptive error message |

### Public API

```python
# config.py
from dataclasses import dataclass, field
import os

@dataclass
class AppConfig:
    duckdb_path: str          # required — from DUCKDB_PATH
    api_key: str              # required — from OPENAI_API_KEY
    model: str                # default: gpt-5.4
    model_lite: str           # default: gpt-5.4-mini
    readonly: bool            # default: True

    def __post_init__(self) -> None:
        """Validate required fields after initialization."""
        ...

def load_config() -> AppConfig:
    """Load AppConfig from environment variables."""
    ...
```

### Test Examples

```python
# tests/test_config.py

def test_config_reads_duckdb_path_from_env(monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", "/data/threat_hunting.db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = load_config()
    assert config.duckdb_path == "/data/threat_hunting.db"

def test_config_default_model_is_gpt_5_4(monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", "/data/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    config = load_config()
    assert config.model == "gpt-5.4"

def test_config_rejects_empty_api_key(monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", "/data/db")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        load_config()
```

### Deliverables

- `agent/config.py` — `AppConfig` dataclass + `load_config()`
- `agent/tests/test_config.py` — 3 passing tests

---

## Phase 2 — `schema.py` (Estimated: 1 h)

**Goal**: Make tests #4–5 green. Provide a human-readable schema description and a column name list for use in the system prompt and SQL validation.

### TDD Cycle

| # | Test Name | Red: What fails | Green: Minimum implementation | Refactor |
|---|---|---|---|---|
| 4 | `test_get_schema_description_returns_string` | `AttributeError`: function undefined | Return a hardcoded multi-line string with column names and types | Format as markdown table for readability |
| 5 | `test_get_column_names_returns_list` | `AssertionError`: empty list | Return a hardcoded `list[str]` of the 17 column names | Derive list from a shared `COLUMNS` constant |

### Public API

```python
# schema.py

CLOUDTRAIL_COLUMNS: list[dict] = [
    {"name": "event_time",               "type": "TIMESTAMP", "nullable": False},
    {"name": "event_name",               "type": "VARCHAR",   "nullable": False},
    {"name": "event_source",             "type": "VARCHAR",   "nullable": False},
    {"name": "aws_region",               "type": "VARCHAR",   "nullable": False},
    {"name": "source_ip_address",        "type": "VARCHAR",   "nullable": True},
    {"name": "user_agent",               "type": "VARCHAR",   "nullable": True},
    {"name": "user_identity_type",       "type": "VARCHAR",   "nullable": True},
    {"name": "user_identity_arn",        "type": "VARCHAR",   "nullable": True},
    {"name": "user_identity_account_id", "type": "VARCHAR",   "nullable": True},
    {"name": "request_parameters",       "type": "JSON",      "nullable": True},
    {"name": "response_elements",        "type": "JSON",      "nullable": True},
    {"name": "error_code",               "type": "VARCHAR",   "nullable": True},
    {"name": "error_message",            "type": "VARCHAR",   "nullable": True},
    {"name": "read_only",                "type": "BOOLEAN",   "nullable": True},
    {"name": "event_type",               "type": "VARCHAR",   "nullable": True},
    {"name": "recipient_account_id",     "type": "VARCHAR",   "nullable": True},
    {"name": "raw_event",                "type": "JSON",      "nullable": False},
]

def get_schema_description() -> str:
    """Return a human-readable markdown-table description of cloudtrail_events."""
    ...

def get_column_names() -> list[str]:
    """Return the list of column names for cloudtrail_events."""
    ...
```

### Deliverables

- `agent/schema.py` — `CLOUDTRAIL_COLUMNS`, `get_schema_description()`, `get_column_names()`
- `agent/tests/test_schema.py` — 2 passing tests

---

## Phase 3 — `query.py` (Estimated: 2 h)

**Goal**: Make tests #6–11 green. Implement safe DuckDB query execution with READ_ONLY enforcement, keyword filtering, EXPLAIN validation, result limiting, and timeout protection.

### Security Rules

1. **READ_ONLY connection**: `duckdb.connect(path, read_only=True)` — never `READ_WRITE`.
2. **Keyword filter**: Reject SQL containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` (case-insensitive, whole-word matching recommended).
3. **EXPLAIN validation**: Run `EXPLAIN <sql>` before execution to catch syntax errors without side effects.
4. **Result limit**: Append `LIMIT 1000` if no `LIMIT` clause is already present.
5. **Timeout**: Use `concurrent.futures.ThreadPoolExecutor` + `Future.result(timeout=30)` to enforce the 30-second limit.

### TDD Cycle

| # | Test Name | Red: What fails | Green: Minimum implementation | Refactor |
|---|---|---|---|---|
| 6  | `test_connect_duckdb_readonly` | `AttributeError`: function undefined | Call `duckdb.connect(path, read_only=True)`; return connection | Add type annotation `-> duckdb.DuckDBPyConnection` |
| 7  | `test_execute_select_query` | `AttributeError`: function undefined | Execute SQL with `.df()` (returns pandas DataFrame) using `tmp_duckdb` fixture | Extract `_execute_unsafe()` private helper |
| 8  | `test_execute_query_returns_empty_dataframe_for_no_results` | `AssertionError`: returns None | Return empty DataFrame (`pd.DataFrame()`) when result is empty | Verify `isinstance(result, pd.DataFrame)` |
| 9  | `test_validate_query_with_explain` | `AttributeError`: function undefined | Run `conn.execute(f"EXPLAIN {sql}")` without errors | Wrap in try/except; raise `QueryValidationError` on failure |
| 10 | `test_validate_query_rejects_write_statements` | No exception raised for `INSERT` | Check SQL for forbidden keywords before EXPLAIN; raise `QueryValidationError` | Use compiled regex for performance |
| 11 | `test_execute_query_timeout` | No timeout raised | Wrap execution in `ThreadPoolExecutor`; call `future.result(timeout=30)` | Extract `QUERY_TIMEOUT_SECONDS = 30` constant |

### Public API

```python
# query.py
import duckdb
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

QUERY_TIMEOUT_SECONDS: int = 30
DEFAULT_ROW_LIMIT: int = 1000

class QueryValidationError(Exception):
    """Raised when a SQL query fails safety validation."""

def connect_duckdb(path: str) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection in READ_ONLY mode."""
    ...

def validate_query(conn: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Validate SQL safety (keyword filter + EXPLAIN). Raises QueryValidationError."""
    ...

def execute_query(conn: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    """Validate and execute SQL; return results as a DataFrame."""
    ...
```

### Test Examples

```python
# tests/test_query.py

def test_connect_duckdb_readonly(tmp_duckdb):
    conn = connect_duckdb(tmp_duckdb)
    assert conn is not None
    conn.close()

def test_execute_select_query(tmp_duckdb):
    conn = connect_duckdb(tmp_duckdb)
    df = execute_query(conn, "SELECT event_name FROM cloudtrail_events LIMIT 5")
    assert isinstance(df, pd.DataFrame)
    assert "event_name" in df.columns
    conn.close()

def test_validate_query_rejects_write_statements(tmp_duckdb):
    conn = connect_duckdb(tmp_duckdb)
    for stmt in ["INSERT INTO foo VALUES (1)", "DROP TABLE cloudtrail_events",
                 "DELETE FROM cloudtrail_events", "UPDATE cloudtrail_events SET x=1"]:
        with pytest.raises(QueryValidationError):
            validate_query(conn, stmt)
    conn.close()

def test_execute_query_timeout(tmp_duckdb, monkeypatch):
    import concurrent.futures
    monkeypatch.setattr(concurrent.futures.Future, "result",
                        lambda self, timeout: (_ for _ in ()).throw(
                            concurrent.futures.TimeoutError()))
    conn = connect_duckdb(tmp_duckdb)
    with pytest.raises(TimeoutError):
        execute_query(conn, "SELECT 1")
    conn.close()
```

### Deliverables

- `agent/query.py` — `connect_duckdb()`, `validate_query()`, `execute_query()`, `QueryValidationError`
- `agent/tests/test_query.py` — 6 passing tests

---

## Phase 4 — `llm.py` (Estimated: 2 h)

**Goal**: Make tests #12–17 green. Implement OpenAI-powered SQL generation and result analysis with proper prompt construction, Markdown fence stripping, and error handling.

### OpenAI Mocking Strategy

All tests that call the OpenAI API MUST use the `mock_openai_client` fixture from `conftest.py`. Never call the real API in tests.

```python
# Example: how tests reference the mock
def test_generate_sql_returns_sql_string(mock_openai_client):
    sql = generate_sql("Show me all CreateUser events", api_key="sk-test")
    assert "SELECT" in sql.upper()
    assert "cloudtrail_events" in sql
```

### TDD Cycle

| # | Test Name | Red: What fails | Green: Minimum implementation | Refactor |
|---|---|---|---|---|
| 12 | `test_build_system_prompt_includes_schema` | `AttributeError`: function undefined | Format `SYSTEM_PROMPT` template with `get_schema_description()` output | Extract schema injection as a standalone step |
| 13 | `test_build_system_prompt_includes_duckdb_dialect` | `AssertionError`: text missing | Ensure `"DuckDB"` appears in the generated prompt | Add dialect note to `SYSTEM_PROMPT` constant |
| 14 | `test_generate_sql_returns_sql_string` | `AttributeError`: function undefined | Call `client.chat.completions.create()`; return `choices[0].message.content` | Extract `_create_chat_completion()` helper |
| 15 | `test_generate_sql_strips_markdown_fences` | `AssertionError`: fences present in result | Strip ` ```sql ` / ` ``` ` with `re.sub()` after receiving LLM response | Handle both ` ```sql ` and ` ``` ` variants |
| 16 | `test_generate_analysis_returns_markdown` | `AttributeError`: function undefined | Call LLM with results serialized to a markdown table; return response text | Limit DataFrame to 50 rows for prompt size |
| 17 | `test_generate_sql_handles_api_error` | Exception propagates uncaught | Catch `openai.OpenAIError`; return user-friendly error string | Add logging with `logging.exception()` |

### Public API

```python
# llm.py
import openai
import pandas as pd

def build_system_prompt() -> str:
    """Build the system prompt including the CloudTrail schema description."""
    ...

def generate_sql(user_query: str, api_key: str, model: str = "gpt-5.4") -> str:
    """Generate a DuckDB SQL query from a natural language question."""
    ...

def generate_analysis(
    sql: str,
    results: pd.DataFrame,
    api_key: str,
    model: str = "gpt-5.4",
) -> str:
    """Generate Markdown analysis text for SQL query results."""
    ...
```

### Markdown Fence Stripping Logic

```python
import re

def _strip_markdown_fences(text: str) -> str:
    """Remove ```sql ... ``` or ``` ... ``` wrappers from LLM output."""
    text = re.sub(r"^```(?:sql)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    return text.strip()
```

### Deliverables

- `agent/llm.py` — `build_system_prompt()`, `generate_sql()`, `generate_analysis()`
- `agent/prompts/system_prompt.py` — `SYSTEM_PROMPT` template constant
- `agent/tests/test_llm.py` — 6 passing tests

---

## Phase 5 — `report.py` (Estimated: 1.5 h)

**Goal**: Make tests #18–21 green. Generate structured threat hunting reports in Markdown format containing all queries, results, analysis, and a generation timestamp. Sensitive data in results must be redacted.

### TDD Cycle

| # | Test Name | Red: What fails | Green: Minimum implementation | Refactor |
|---|---|---|---|---|
| 18 | `test_generate_report_markdown` | `AttributeError`: function undefined | Iterate over a list of `ReportEntry` objects; render each as a Markdown section | Extract `_render_entry()` helper |
| 19 | `test_report_includes_timestamp` | `AssertionError`: timestamp missing | Insert `datetime.now(UTC).isoformat()` in report header | Use `datetime.now(timezone.utc)` for timezone-aware output |
| 20 | `test_report_includes_all_queries` | `AssertionError`: query text missing | Ensure each `entry.sql` is rendered in a ` ```sql ``` ` block | Verify entry count matches section count |
| 21 | `test_report_sanitizes_sensitive_data` | Sensitive string appears in output | Apply regex redaction for patterns matching AWS secret keys / access key IDs | Define `SENSITIVE_PATTERNS` list for extensibility |

### Public API

```python
# report.py
from dataclasses import dataclass
import pandas as pd

@dataclass
class ReportEntry:
    """A single query-result-analysis triple in an investigation session."""
    sql: str
    results: pd.DataFrame
    analysis: str

def generate_report(entries: list[ReportEntry], title: str = "Threat Hunting Report") -> str:
    """Generate a Markdown threat hunting report from a list of ReportEntries."""
    ...
```

### Sensitive Data Redaction Patterns

```python
# Patterns for AWS credential-like strings
SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    # AWS Secret Access Key (40-char base64-like)
    (r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])", "[REDACTED_SECRET]"),
    # AWS Access Key ID
    (r"(AKIA|ASIA|AROA|AIDA)[A-Z0-9]{16}", "[REDACTED_KEY_ID]"),
]
```

### Report Markdown Structure

```markdown
# Threat Hunting Report

**Generated:** 2026-03-11T12:00:00+00:00

---

## Query 1

### SQL

```sql
SELECT event_name, COUNT(*) as cnt
FROM cloudtrail_events
GROUP BY event_name ORDER BY cnt DESC LIMIT 10
```

### Results

| event_name | cnt |
|------------|-----|
| ...        | ... |

### Analysis

> ... AI-generated analysis text ...

---
```

### Deliverables

- `agent/report.py` — `ReportEntry`, `generate_report()`
- `agent/tests/test_report.py` — 4 passing tests

---

## Phase 6 — `app.py` (Estimated: 1.5 h)

**Goal**: Make test #22 green and implement the full Streamlit UI satisfying AGT-01 through AGT-09.

### TDD Cycle

| # | Test Name | Red: What fails | Green: Minimum implementation | Refactor |
|---|---|---|---|---|
| 22 | `test_session_state_initialization` | `AttributeError`: session state keys missing | Define `_init_session_state()` that populates `st.session_state` with required keys | Call `_init_session_state()` at the top of `app.py` |

### Required Session State Keys

```python
SESSION_STATE_DEFAULTS: dict = {
    "messages": [],          # chat history: list of {role, content}
    "query_history": [],     # list of ReportEntry for report generation
    "last_sql": "",          # most recently generated SQL (editable)
    "last_results": None,    # pandas DataFrame or None
    "last_analysis": "",     # AI analysis text
    "api_key": "",           # entered in sidebar (AGT-09)
    "model": "gpt-5.4",      # selected model
}
```

### UI Component Map (AGT-01 through AGT-09)

| Requirement | Streamlit Component | Location |
|---|---|---|
| AGT-01: Chat input | `st.chat_input()` + `st.chat_message()` | Main area |
| AGT-02: SQL generation | `generate_sql()` called on submit | On message send |
| AGT-03: SQL review & edit | `st.code_editor()` or `st.text_area()` | Main area, below SQL |
| AGT-04: Tabular results | `st.dataframe()` | Main area, below edit |
| AGT-05: Analysis comments | `st.markdown()` | Main area, below results |
| AGT-06: Report generation | `st.download_button()` | Sidebar or main |
| AGT-07: Preset prompts | `st.selectbox()` in sidebar | Sidebar |
| AGT-08: Session save/recall | `st.session_state` + `json.dump` | Sidebar buttons |
| AGT-09: API key config | `st.text_input(type="password")` | Sidebar |

### Preset Threat Hunting Prompts (AGT-07)

```python
PRESET_PROMPTS: list[str] = [
    "List all API calls executed for the first time within the past 24 hours.",
    "Identify IAM users with a high number of failed console login attempts.",
    "Extract all actions performed by the root account.",
    "Detect API calls made during anomalous hours (e.g., late night).",
    "List newly created IAM users and access keys.",
]
```

### app.py Skeleton

```python
"""Streamlit entry point for the THuntCloud AI threat hunting agent."""

import streamlit as st

from config import load_config
from llm import generate_sql, generate_analysis
from query import connect_duckdb, execute_query, QueryValidationError
from report import ReportEntry, generate_report

PRESET_PROMPTS: list[str] = [ ... ]

SESSION_STATE_DEFAULTS: dict = { ... }


def _init_session_state() -> None:
    """Initialize Streamlit session state with default values."""
    for key, default in SESSION_STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def render_sidebar() -> None:
    """Render sidebar: API key config, model selection, preset prompts, report download."""
    ...


def render_chat() -> None:
    """Render main chat area: message history, SQL editor, results table, analysis."""
    ...


def main() -> None:
    st.set_page_config(page_title="THuntCloud", page_icon="🔍", layout="wide")
    _init_session_state()
    render_sidebar()
    render_chat()


if __name__ == "__main__":
    main()
```

### test_session_state_initialization

```python
# tests/test_app.py
from unittest.mock import patch, MagicMock

def test_session_state_initialization():
    """Session state is populated with expected keys on startup."""
    mock_state = {}
    with patch("streamlit.session_state", mock_state):
        from app import _init_session_state, SESSION_STATE_DEFAULTS
        _init_session_state()
        for key in SESSION_STATE_DEFAULTS:
            assert key in mock_state
```

### Deliverables

- `agent/app.py` — `_init_session_state()`, `render_sidebar()`, `render_chat()`, `main()`
- `agent/tests/test_app.py` — 1 passing test (manual/integration testing for full UI)

---

## Dependency Graph

```
app.py
  ├── config.py
  ├── llm.py
  │   ├── prompts/system_prompt.py
  │   └── schema.py
  ├── query.py
  │   └── schema.py (optional — for column validation)
  └── report.py
```

---

## Commit Convention Examples

Following Conventional Commits format (required by project rules):

```
feat(agent): add AppConfig with env var loading (test #1-3)
feat(agent): add CloudTrail schema description (test #4-5)
feat(agent): add DuckDB query execution with READ_ONLY mode (test #6-8)
feat(agent): add SQL safety validation with keyword filter (test #9-11)
feat(agent): add LLM SQL generation with system prompt (test #12-15)
feat(agent): add LLM result analysis (test #16-17)
feat(agent): add threat hunting report generation (test #18-21)
feat(agent): add Streamlit UI entry point (test #22)
refactor(agent): extract shared helpers across query and llm modules
docs(agent): update AGENT_IMPLEMENTATION_PLAN.md with completed phases
```

---

## Risks and Notes

| Risk | Mitigation |
|------|------------|
| DuckDB `read_only=True` rejects connection when ingester holds write lock | Document startup order in README; run ingester before agent |
| OpenAI API `gpt-5.4` model availability | Fall back to `gpt-4o` if `gpt-5.4` is unavailable; make model configurable |
| Large query results (>1000 rows) causing Streamlit memory issues | Enforce `DEFAULT_ROW_LIMIT = 1000`; truncate before rendering |
| Markdown fence stripping edge cases (e.g., nested fences) | Unit test with multiple LLM response variations |
| Streamlit session state not persisted across container restarts | Use `st.session_state` for in-session only; export sessions as JSON files for AGT-08 |
| `test_execute_query_timeout` flakiness in CI | Use monkeypatch to mock `Future.result()`; avoid real sleeps in tests |

---

*This document is generated from PRD.md §6.2 and agent/AGENTS.md. It should be updated as each phase is completed.*

