# agent

AI-assisted threat hunting module for THuntCloud.

Enter a natural language question → OpenAI generates DuckDB SQL → results are executed against the
CloudTrail log database → AI delivers a threat analysis summary.
DuckDB is always opened in **`READ_ONLY`** mode.

---

## Quick Start

```bash
# Run from docker/
docker compose up -d agent

# Open the UI
open http://localhost:8501
```

`OPENAI_API_KEY` is required for SQL generation and analysis.
Built-in hunts with a `sql` field can be executed without an API key.

---

## Module Structure

```
agent/
├── app.py                 # Streamlit entry point
├── llm.py                 # OpenAI API integration (SQL generation + analysis)
├── query.py               # Query execution, validation, date filter, row limit
├── report.py              # Report generation (Markdown + sensitive data redaction)
├── schema.py              # CloudTrail table schema definitions
├── config.py              # Configuration management (env vars)
├── builtin_hunts.yaml     # Pre-built threat hunting queries
├── prompts/
│   └── system_prompt.py   # System prompt template for SQL generation
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
└── tests/
    ├── conftest.py        # Shared fixtures (mock_openai_client, tmp_duckdb)
    ├── test_config.py
    ├── test_schema.py
    ├── test_query.py
    ├── test_llm.py
    ├── test_report.py
    └── test_app.py
```

---

## SQL Safety Guards

Before executing any LLM-generated SQL, `query.py` applies three guards:

1. **Keyword blocklist** — rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`.
2. **EXPLAIN validation** — runs `EXPLAIN <sql>` on the READ_ONLY connection first.
3. **Row-limit cap** — wraps queries without a `LIMIT` in `SELECT * FROM (...) LIMIT 1000`.

---

## Built-in Hunts

`builtin_hunts.yaml` ships categorised queries with `label`, `description`, `prompt`, and an optional `sql` field.

- Entries **with** `sql` — run directly, no API key needed.
- Entries **without** `sql` — require OpenAI API key to generate SQL.

---

## Configuration

| Variable            | Required | Default        | Description                  |
|---------------------|----------|----------------|------------------------------|
| `OPENAI_API_KEY`    | Yes      | —              | OpenAI API key               |
| `DUCKDB_PATH`       | Yes      | —              | Path to DuckDB file          |
| `OPENAI_MODEL`      | No       | `gpt-5.4`      | Model for SQL gen + analysis |
| `OPENAI_MODEL_LITE` | No       | `gpt-5.4-mini` | Lighter model (optional)     |

---

## Development

```bash
cd agent
pip install -r requirements.txt -r requirements-dev.txt

pytest                              # Run all tests
pytest --cov=. --cov-report=term-missing  # With coverage
ruff check .                        # Lint
black .                             # Format
```
