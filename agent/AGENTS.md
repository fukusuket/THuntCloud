# AGENTS.md — Agent Module (Python / Streamlit)

> This file provides GitHub Copilot with module-specific context for the `agent` module.
> For project-wide instructions, see [../.github/AGENTS.md](../.github/AGENTS.md).
> For feature requirements and priorities, see [../doc/PRD.md](../doc/PRD.md) — Section 6.2 (agent Module).

## Module Purpose

The agent provides an interactive Streamlit UI for AI-assisted threat hunting. Users enter natural language questions, the AI generates DuckDB SQL queries, executes them, and provides analysis. It also supports automated report generation and built-in preset queries.

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

## Module Structure

```
agent/
├── app.py                 # Streamlit entry point
├── llm.py                 # OpenAI API integration (SQL generation + analysis)
├── query.py               # DuckDB query execution, validation, date filter, row limit
├── report.py              # Threat hunting report generation (Markdown + sensitive data redaction)
├── schema.py              # CloudTrail table schema definitions (column list, descriptions)
├── config.py              # Configuration management (env vars)
├── builtin_hunts.yaml     # Pre-built threat hunting queries (categorised, label/prompt/sql)
├── prompts/
│   ├── __init__.py
│   └── system_prompt.py   # System prompt template for SQL generation
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Dev/test dependencies
├── Dockerfile
├── pytest.ini             # Sets pythonpath = . so modules resolve as `llm`, not `agent.llm`
├── tests/
│   ├── __init__.py
│   ├── conftest.py        # Shared fixtures (mock_openai_client, tmp_duckdb)
│   ├── test_config.py
│   ├── test_schema.py
│   ├── test_query.py
│   ├── test_llm.py
│   ├── test_report.py
│   └── test_app.py        # Streamlit session state tests
└── AGENTS.md              ← You are here
```

## Implemented Tests

### config.py
1. `test_config_reads_duckdb_path_from_env` — Config loads `DUCKDB_PATH` from environment.
2. `test_config_default_model_is_gpt_5_4` — Default model is `gpt-5.4`.
3. `test_config_rejects_empty_api_key` — Raises `ValueError` if `OPENAI_API_KEY` is empty.

### schema.py
4. `test_get_schema_description_returns_string` — Returns a human-readable schema description.
5. `test_get_column_names_returns_list` — Returns the expected column name list.

### query.py
6. `test_connect_duckdb_readonly` — Opens DuckDB in read-only mode.
7. `test_execute_select_query` — Executes `SELECT` and returns a `pd.DataFrame`.
8. `test_execute_query_returns_empty_dataframe_for_no_results` — Empty result → empty DataFrame.
9. `test_validate_query_with_explain` — `EXPLAIN <sql>` succeeds on valid SQL.
10. `test_validate_query_rejects_write_statements` — `INSERT`/`UPDATE`/`DELETE`/`DROP` rejected.
11. `test_execute_query_timeout` — Queries exceeding 30 s raise a timeout error.
12. `test_apply_date_filter_both_bounds` — CTE injected with both start/end date.
13. `test_apply_date_filter_no_bounds` — No dates → original SQL unchanged.
14. `test_apply_row_limit_adds_limit` — Queries without `LIMIT` get capped at 1000 rows.
15. `test_apply_row_limit_preserves_existing_limit` — Existing `LIMIT` not doubled.

### llm.py
16. `test_build_system_prompt_includes_schema` — System prompt includes schema description.
17. `test_generate_sql_returns_sql_string` — Mocked OpenAI response → SQL string returned.
18. `test_generate_sql_strips_markdown_fences` — ` ```sql ... ``` ` wrappers stripped.
19. `test_generate_analysis_returns_markdown` — Query results → Markdown analysis.
20. `test_generate_sql_handles_api_error` — `OpenAIError` caught → user-friendly message.

### report.py
21. `test_generate_report_markdown` — Session produces Markdown report.
22. `test_report_includes_timestamp` — Report header contains generation timestamp.
23. `test_report_includes_all_queries` — All query/result/analysis triples included.
24. `test_report_sanitizes_sensitive_data` — AWS key IDs and secrets redacted.

### app.py
25. `test_session_state_initialization` — Session state has expected keys on startup.

## OpenAI API Mocking Strategy

All tests involving OpenAI API calls MUST use mocks. Never call the real API in tests.

**Important**: `pytest.ini` sets `pythonpath = .`, so mock the module as `llm.OpenAI`, **not** `agent.llm.OpenAI`.

```python
# agent/tests/conftest.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client that returns a predefined SQL response."""
    with patch("llm.OpenAI") as mock_cls:          # <-- 'llm.OpenAI', not 'agent.llm.OpenAI'
        client = MagicMock()
        mock_cls.return_value = client

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = (
            "SELECT event_name, COUNT(*) AS cnt "
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
            event_time               TIMESTAMP,
            event_name               VARCHAR,
            event_source             VARCHAR,
            aws_region               VARCHAR,
            source_ip_address        VARCHAR,
            user_agent               VARCHAR,
            user_identity_type       VARCHAR,
            user_identity_arn        VARCHAR,
            user_identity_account_id VARCHAR,
            request_parameters       VARCHAR,   -- stored as VARCHAR, not JSON type
            response_elements        VARCHAR,
            error_code               VARCHAR,
            error_message            VARCHAR,
            read_only                BOOLEAN,
            event_type               VARCHAR,
            recipient_account_id     VARCHAR,
            raw_event                VARCHAR    -- full original event JSON as VARCHAR
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

## SQL Safety Rules

1. **READ_ONLY connection**: `duckdb.connect(..., read_only=True)` always.
2. **Keyword blocklist**: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` rejected (regex, word-boundary).
3. **EXPLAIN validation**: `EXPLAIN <sql>` runs before execution.
4. **Row-limit cap**: Queries without `LIMIT` are wrapped in `SELECT * FROM (...) LIMIT 1000`.
5. **Timeout**: Queries are limited to `QUERY_TIMEOUT_SECONDS = 30` seconds.

## Environment Variables

| Variable            | Default           | Description                                      |
| ------------------- | ----------------- | ------------------------------------------------ |
| `DUCKDB_PATH`       | (required)        | Path to the DuckDB database file                 |
| `OPENAI_API_KEY`    | (required)        | OpenAI API key                                   |
| `OPENAI_MODEL`      | `gpt-5.4`         | Model for SQL generation and analysis            |
| `OPENAI_MODEL_LITE` | `gpt-5.4-mini`    | Lightweight model for quick tasks                |
| `DUCKDB_READONLY`   | `true`            | Must be `true` for agent                         |
| `SSL_CERT_FILE`     | —                 | CA bundle path for corporate TLS inspection proxy|
| `REQUESTS_CA_BUNDLE`| —                 | Alternative CA bundle path (same purpose)        |

## Dependencies

**requirements.txt**
```
streamlit>=1.40.0
openai>=1.60.0
duckdb>=1.2.0
pandas>=2.2.0
pyyaml>=6.0.0
tabulate>=0.9.0
httpx>=0.27.0
```

**requirements-dev.txt**
```
pytest>=8.0.0
pytest-mock>=3.14.0
ruff>=0.9.0
black>=24.0.0
```

## Language Policy

- **All Python docstrings, inline comments, type annotations, and documentation MUST be written in English.**
