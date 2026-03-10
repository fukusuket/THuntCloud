# AGENTS.md — Agent Module (Python / Streamlit)

> This file provides GitHub Copilot with module-specific context for the `agent` module.
> For project-wide instructions, see [../.github/AGENTS.md](../.github/AGENTS.md).
> For feature requirements and priorities, see [../doc/PRD.md](../doc/PRD.md) — Section 6.2 (agent Module).

## Module Purpose

The agent provides an interactive Streamlit UI for AI-assisted threat hunting. Users enter natural language questions, the AI generates DuckDB SQL queries, executes them, and provides analysis. It also supports automated report generation.

**DuckDB is always opened in `READ_ONLY` mode in this module.**

## Technology Stack

| Item              | Value                                    |
| ----------------- | ---------------------------------------- |
| Language          | Python 3.12+                             |
| Framework         | Streamlit                                |
| AI Integration    | OpenAI API (`gpt-5.4` default, see PRD §11.2) |
| DB Client         | `duckdb` Python package                  |
| Data Processing   | `pandas`                                 |
| Test Framework    | `pytest`, `pytest-mock`                  |
| Linter            | `ruff`                                   |
| Formatter         | `black`                                  |

## Planned Module Structure

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
├── requirements.txt       # Python dependencies
├── tests/
│   ├── conftest.py        # Shared fixtures
│   ├── test_llm.py        # LLM integration tests (mocked)
│   ├── test_query.py      # DuckDB query tests
│   ├── test_report.py     # Report generation tests
│   ├── test_schema.py     # Schema helper tests
│   └── test_config.py     # Config tests
└── AGENTS.md              ← You are here
```

## TDD Test List

When implementing the agent, follow this ordered test list. Each item should be a `def test_*` function in pytest. Proceed one test at a time using Red-Green-Refactor.

### config.py

1. `test_config_reads_duckdb_path_from_env` — Config loads `DUCKDB_PATH` from environment variables.
2. `test_config_default_model_is_gpt_5_4` — Default model is `gpt-5.4` when `OPENAI_MODEL` is unset.
3. `test_config_rejects_empty_api_key` — Raises error if `OPENAI_API_KEY` is empty.

### schema.py

4. `test_get_schema_description_returns_string` — Returns a human-readable description of the `cloudtrail_events` table.
5. `test_get_column_names_returns_list` — Returns the expected list of column names.

### query.py

6. `test_connect_duckdb_readonly` — Opens DuckDB in read-only mode successfully.
7. `test_execute_select_query` — Executes a simple `SELECT` and returns a pandas DataFrame.
8. `test_execute_query_returns_empty_dataframe_for_no_results` — Empty result returns an empty DataFrame, not an error.
9. `test_validate_query_with_explain` — Running `EXPLAIN <sql>` before execution does not raise on valid SQL.
10. `test_validate_query_rejects_write_statements` — `INSERT`, `UPDATE`, `DELETE`, `DROP` statements are rejected before execution.
11. `test_execute_query_timeout` — Queries exceeding the timeout limit raise an appropriate error.

### llm.py

12. `test_build_system_prompt_includes_schema` — The system prompt includes the CloudTrail table schema.
13. `test_build_system_prompt_includes_duckdb_dialect` — The system prompt specifies DuckDB SQL dialect.
14. `test_generate_sql_returns_sql_string` — Given a mocked OpenAI response, `generate_sql()` returns a SQL string.
15. `test_generate_sql_strips_markdown_fences` — If the LLM wraps SQL in ```sql ... ```, the fences are stripped.
16. `test_generate_analysis_returns_markdown` — Given query results, `generate_analysis()` returns Markdown analysis text.
17. `test_generate_sql_handles_api_error` — OpenAI API errors are caught and surfaced as user-friendly messages.

### report.py

18. `test_generate_report_markdown` — Given a session (queries + results + analysis), generates a Markdown report.
19. `test_report_includes_timestamp` — The report header includes the generation timestamp.
20. `test_report_includes_all_queries` — Each query-result-analysis triple is included in the report.
21. `test_report_sanitizes_sensitive_data` — API keys or credentials in query results are redacted.

### app.py (Streamlit integration — manual testing primarily)

22. `test_session_state_initialization` — Session state contains expected keys on startup.

## OpenAI API Mocking Strategy

All tests that involve OpenAI API calls MUST use mocks. Never call the real API in tests.

```python
# conftest.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client that returns a predefined SQL response."""
    with patch("agent.llm.OpenAI") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client

        # Default response: a simple SELECT query
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
    """Create a temporary DuckDB with the cloudtrail_events table and sample data."""
    import duckdb

    db_path = tmp_path / "test.db"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE cloudtrail_events (
            event_time           TIMESTAMP,
            event_name           VARCHAR,
            event_source         VARCHAR,
            aws_region           VARCHAR,
            source_ip_address    VARCHAR,
            user_agent           VARCHAR,
            user_identity_type   VARCHAR,
            user_identity_arn    VARCHAR,
            user_identity_account_id VARCHAR,
            request_parameters   JSON,
            response_elements    JSON,
            error_code           VARCHAR,
            error_message        VARCHAR,
            read_only            BOOLEAN,
            event_type           VARCHAR,
            recipient_account_id VARCHAR,
            raw_event            JSON
        )
    """)
    # Insert sample data
    conn.execute("""
        INSERT INTO cloudtrail_events (event_time, event_name, event_source, aws_region)
        VALUES
            ('2024-01-15 10:30:00', 'DescribeInstances', 'ec2.amazonaws.com', 'us-east-1'),
            ('2024-01-15 10:31:00', 'DescribeInstances', 'ec2.amazonaws.com', 'us-east-1'),
            ('2024-01-15 10:32:00', 'CreateUser', 'iam.amazonaws.com', 'us-east-1')
    """)
    conn.close()
    yield str(db_path)
```

## System Prompt Template (Reference)

```python
SYSTEM_PROMPT = """You are a DuckDB SQL expert specializing in AWS CloudTrail log analysis.

You have access to a table called `cloudtrail_events` with the following schema:

{schema}

Rules:
1. Generate ONLY DuckDB-compatible SQL. Do not use MySQL or PostgreSQL-specific syntax.
2. Always use the table name `cloudtrail_events`.
3. Return ONLY the SQL query, no explanation.
4. Use appropriate WHERE clauses to filter relevant events.
5. For time-based queries, `event_time` is a TIMESTAMP column.
6. Use JSON extraction functions for `request_parameters`, `response_elements`, and `raw_event` columns.
7. Limit results to 1000 rows unless the user specifically asks for more.
8. Never generate INSERT, UPDATE, DELETE, DROP, or any DDL/DML statements.
"""
```

## SQL Safety Rules

1. **READ_ONLY connection**: The DuckDB connection is always opened with `read_only=True`.
2. **Pre-execution validation**: Before executing any AI-generated SQL:
   - Check that the SQL does not contain `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` keywords (case-insensitive).
   - Run `EXPLAIN <sql>` to verify it's valid.
3. **Result size limits**: Default `LIMIT 1000` on all queries.
4. **Timeout**: Queries are limited to 30 seconds.

## Environment Variables

| Variable           | Default       | Description                              |
| ------------------ | ------------- | ---------------------------------------- |
| `DUCKDB_PATH`      | (required)    | Path to the DuckDB database file         |
| `DUCKDB_READONLY`  | `true`        | Must be `true` for agent                 |
| `OPENAI_API_KEY`   | (required)    | OpenAI API key                           |
| `OPENAI_MODEL`     | `gpt-5.4`     | Model for SQL generation and analysis    |
| `OPENAI_MODEL_LITE`| `gpt-5.4-mini`| Lightweight model for quick tasks        |

## Language Policy

- **All Python docstrings, inline comments, type annotations, and documentation MUST be written in English.**
- Non-English text is not permitted in code comments, commit messages, or PR descriptions.

## Dependencies (requirements.txt)

```
streamlit>=1.40.0
openai>=1.60.0
duckdb>=1.2.0
pandas>=2.2.0
```

### Dev Dependencies (requirements-dev.txt)

```
pytest>=8.0.0
pytest-mock>=3.14.0
ruff>=0.9.0
black>=24.0.0
```

