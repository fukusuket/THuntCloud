# AGENTS.md — THuntCloud

AI coding agent guide for the THuntCloud project. For module-level detail see
[ingester/AGENTS.md](ingester/AGENTS.md) and [agent/AGENTS.md](agent/AGENTS.md).

## Architecture at a Glance

Three Docker containers share one DuckDB file via a **bind mount** (`docker/data/db/threat_hunting.db`).

| Container | Language | DuckDB mode | Port |
|-----------|----------|-------------|------|
| `ingester` | Rust 1.85+ | **READ_WRITE** (sole writer) | — |
| `agent` | Python 3.12+ / Streamlit | READ_ONLY | 8501 |
| `dashboard` | Apache Superset | READ_ONLY | 8088 |

The bind-mount (not a named volume) is intentional — Docker Engine on Linux/WSL2 misresolves relative paths for named-volume `driver_opts`, so each service declares its own `volumes:` entry in `docker/docker-compose.yml`.

`ingester` must finish before `agent`/`dashboard` start. They cannot run concurrently with an active write session.

## Essential Commands (run from `docker/`)

```bash
# First-time ingest
docker compose --profile ingest run --rm ingester ingest --path /data/logs

# Start agent + dashboard
docker compose up -d --build

# Re-ingest from scratch
docker compose down
rm -f data/db/threat_hunting.db data/db/threat_hunting.db.wal
docker compose --profile ingest run --rm ingester ingest --path /data/logs
docker compose up -d --build

# Fix blank dashboard after re-ingest (re-syncs column metadata)
docker compose --profile resync run --rm superset-resync
```

## Development Workflows

```bash
# Rust (ingester/)
cargo test        # unit + integration tests
cargo clippy      # lint
cargo fmt         # format

# Python (agent/)
pytest            # all tests
ruff check .      # lint
black .           # format
```

**TDD is mandatory.** Write one failing test first, then the minimum code to pass it.
Never write production code without a corresponding failing test.

## Key Project Conventions

- **All comments, docstrings, and commit messages must be in English.**
- **Rust errors:** use `anyhow::Result` everywhere; add context with `.with_context(|| ...)`.
- **Rust DB writes:** always use `duckdb::Appender` (not individual INSERTs) — see `ingester/src/db.rs`.
- **Python type hints:** required on all function signatures.
- **Python OpenAI mocks:** every test touching `llm.py` must mock `agent.llm.OpenAI`; real API calls in tests are forbidden.
- **Python DuckDB in tests:** use `tmp_path / "test.db"` — see `agent/tests/conftest.py` for the `tmp_duckdb` fixture.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`).

## DuckDB Schema (single table)

`cloudtrail_events` has 17 columns. JSON blobs (`request_parameters`, `response_elements`, `raw_event`) are stored as **VARCHAR**, not DuckDB JSON type. Extract with `json_extract_string(raw_event, '$.key')`.

`ingested_files (file_path PK, sha256, ingested_at)` tracks ingested files for deduplication (SHA-256 checksum).

## SQL Safety in `agent/`

Before executing any LLM-generated SQL, `query.py` applies two guards:

1. **Keyword blocklist** — rejects queries containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` (regex, word-boundary, case-insensitive).
2. **EXPLAIN validation** — runs `EXPLAIN <sql>` on the READ_ONLY connection before the real query.

Date-range UI filters inject a `_ct_filtered` CTE that wraps `cloudtrail_events` and replaces all references to it in the original SQL — see `apply_date_filter()` in `agent/query.py`.

## Ingester CLI Flags

```
ingester ingest --path <dir>
                [--include <glob>]   # e.g. "*CloudTrail*"
                [--exclude <glob>]   # e.g. "*us-west-2*"
                [--from   <YYYYMMDD>]
                [--to     <YYYYMMDD>]
```

Date and path filters operate on the filesystem path (CloudTrail stores logs under `yyyy/mm/dd/` segments). Files without a recognizable date segment are always included.

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `OPENAI_API_KEY` | agent only | — |
| `DUCKDB_PATH` | all | — |
| `OPENAI_MODEL` | agent | `gpt-5.4` |
| `OPENAI_MODEL_LITE` | agent | `gpt-5.4-mini` |
| `DUCKDB_HOST_PATH` | docker host | `./data/db` |
| `SUPERSET_SECRET_KEY` | dashboard | `change-me-in-production` |

