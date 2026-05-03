# AGENTS.md — Agent Module (Python / Streamlit)

> Module-specific TDD context for the `agent` module.
> For project-wide instructions, see the root [AGENTS.md](../AGENTS.md).
> For feature requirements, see [doc/PRD.md](../doc/PRD.md).

## Module Purpose

The agent provides an interactive Streamlit UI for AI-assisted threat hunting.
Users enter natural language questions; the AI generates DuckDB SQL, executes it, and
provides a fact-based analysis summary. It also supports automated report generation
and pre-built preset queries.

**DuckDB is always opened in `READ_ONLY` mode in this module.**

## Technology Stack

| Item | Value |
|------|-------|
| Language | Python 3.12+ |
| Framework | Streamlit |
| AI Integration | OpenAI API (`gpt-5.4` default; `gpt-5.5`, `gpt-5.4-mini` also available) |
| DB Client | `duckdb` Python package |
| Data Processing | `pandas` |
| Test Framework | `pytest`, `pytest-mock` |
| Linter | `ruff` |
| Formatter | `black` |

## Module Structure

```
agent/
├── app.py                 # Streamlit entry point — UI layout, session state, event loop
├── llm.py                 # OpenAI API integration (SQL generation, analysis, SQL fix)
├── query.py               # DuckDB query execution, validation, date filter, row limit, retry
├── report.py              # Threat hunting report generation (Markdown + sensitive data redaction)
├── schema.py              # CloudTrail table schema description for the system prompt
├── config.py              # Configuration management (env vars)
├── builtin_hunts.yaml     # Pre-built threat hunting queries (categorised)
├── prompts/
│   ├── __init__.py
│   └── system_prompt.py   # System prompt template for SQL generation
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── pytest.ini             # Sets pythonpath = . so modules resolve as `llm`, not `agent.llm`
└── tests/
    ├── __init__.py
    ├── conftest.py        # Shared fixtures: mock_openai_client, tmp_duckdb
    ├── test_config.py
    ├── test_schema.py
    ├── test_query.py
    ├── test_llm.py
    ├── test_report.py
    └── test_app.py
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
10. `test_validate_query_rejects_write_statements` — `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`CREATE` rejected.
11. `test_execute_query_timeout` — Queries exceeding `QUERY_TIMEOUT_SECONDS` raise a timeout error.
12. `test_apply_date_filter_both_bounds` — `_ct_filtered` CTE injected with both start/end date.
13. `test_apply_date_filter_start_only` — Only lower bound → single WHERE condition.
14. `test_apply_date_filter_no_bounds` — No dates → original SQL unchanged.
15. `test_apply_date_filter_extends_existing_with` — Existing WITH chain extended, no duplicate WITH.
16. `test_apply_row_limit_adds_limit` — Queries without `LIMIT` are wrapped with `LIMIT N`.
17. `test_apply_row_limit_replaces_existing_limit` — Existing `LIMIT` replaced by caller's value.

### llm.py
18. `test_build_system_prompt_includes_schema` — System prompt includes schema description.
19. `test_generate_sql_returns_sql_string` — Mocked OpenAI response → SQL string returned.
20. `test_generate_sql_strips_markdown_fences` — ` ```sql ... ``` ` wrappers stripped.
21. `test_generate_sql_with_context` — Prior conversation turns injected as message pairs.
22. `test_generate_analysis_returns_markdown` — Query results → Markdown analysis.
23. `test_generate_sql_handles_api_error` — `OpenAIError` caught → user-friendly message.
24. `test_fix_sql_with_llm_returns_corrected_sql` — Broken SQL + error → corrected SQL.

### report.py
25. `test_generate_report_markdown` — Session produces Markdown report.
26. `test_report_includes_timestamp` — Report header contains generation timestamp.
27. `test_report_includes_all_queries` — All query/result/analysis triples included.
28. `test_report_sanitizes_sensitive_data` — AWS ARNs and account IDs redacted.

### app.py
29. `test_session_state_initialization` — Session state has expected keys on startup.
30. `test_model_options_include_gpt_5_5` — `MODEL_OPTIONS` constant includes `gpt-5.5`.

## OpenAI API Mocking Strategy

All tests involving OpenAI API calls MUST use mocks. Never call the real API in tests.

**Important:** `pytest.ini` sets `pythonpath = .`, so mock the module as `llm.OpenAI`,
**not** `agent.llm.OpenAI`.

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
            request_parameters       VARCHAR,
            response_elements        VARCHAR,
            error_code               VARCHAR,
            error_message            VARCHAR,
            read_only                BOOLEAN,
            event_type               VARCHAR,
            recipient_account_id     VARCHAR,
            raw_event                VARCHAR,
            geo_country_code         VARCHAR,
            geo_country_name         VARCHAR,
            geo_city                 VARCHAR,
            geo_latitude             DOUBLE,
            geo_longitude            DOUBLE,
            geo_asn                  VARCHAR,
            geo_org                  VARCHAR
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

1. **READ_ONLY connection:** `duckdb.connect(..., read_only=True)` always.
2. **Keyword blocklist:** `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` rejected (regex, word-boundary, case-insensitive).
3. **EXPLAIN validation:** `EXPLAIN <sql>` runs before execution.
4. **Row-limit cap:** Queries without `LIMIT` are wrapped in `SELECT * FROM (...) AS _limited LIMIT N`. Existing `LIMIT` is replaced so the sidebar setting is always the effective cap.
5. **Timeout:** Queries are cancelled after `QUERY_TIMEOUT_SECONDS = 30` seconds.
6. **Retry:** `execute_with_retry` calls `fix_sql_with_llm` once on `QueryValidationError`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DUCKDB_PATH` | (required) | Path to the DuckDB database file |
| `OPENAI_API_KEY` | (required for AI) | OpenAI API key |
| `OPENAI_MODEL` | `gpt-5.4` | Model for SQL generation and analysis (`gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini` available) |
| `OPENAI_MODEL_LITE` | `gpt-5.4-mini` | Lightweight model (optional) |
| `SSL_CERT_FILE` | — | CA bundle for corporate TLS inspection proxy |
| `REQUESTS_CA_BUNDLE` | — | Alternative CA bundle path (same purpose) |

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
