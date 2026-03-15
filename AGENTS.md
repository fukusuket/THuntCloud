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
- **Python OpenAI mocks:** every test touching `llm.py` must mock `llm.OpenAI` (not `agent.llm.OpenAI` — `pytest.ini` sets `pythonpath = .` so modules resolve as `llm`, not `agent.llm`); real API calls in tests are forbidden.
- **Python DuckDB in tests:** use `tmp_path / "test.db"` — see `agent/tests/conftest.py` for the `tmp_duckdb` fixture.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`).

## DuckDB Schema (single table)

`cloudtrail_events` has 17 columns. JSON blobs (`request_parameters`, `response_elements`, `raw_event`) are stored as **VARCHAR**, not DuckDB JSON type. Extract with `json_extract_string(raw_event, '$.key')`.

`ingested_files (file_path PK, sha256, ingested_at)` tracks ingested files for deduplication (SHA-256 checksum).

## SQL Safety in `agent/`

Before executing any LLM-generated SQL, `query.py` applies three guards:

1. **Keyword blocklist** — rejects queries containing `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` (regex, word-boundary, case-insensitive).
2. **EXPLAIN validation** — runs `EXPLAIN <sql>` on the READ_ONLY connection before the real query.
3. **Row-limit cap** — `apply_row_limit()` wraps any query that has no `LIMIT` clause in `SELECT * FROM (...) AS _limited LIMIT 1000` to prevent unbounded result sets.

Date-range UI filters inject a `_ct_filtered` CTE that wraps `cloudtrail_events` and replaces all references to it in the original SQL — see `apply_date_filter()` in `agent/query.py`.

`agent/builtin_hunts.yaml` ships pre-built threat hunting queries (categorised, with `label`, `description`, `prompt`, and an optional `sql` field). Entries with a `sql` field can be executed directly without an OpenAI API key; entries with only a `prompt` require one.

## Ingester CLI Flags

```
ingester ingest --path <dir>
                [--db     <path>]    # DuckDB file path (overrides DUCKDB_PATH env var)
                [--include <globs>]  # comma-separated globs, e.g. "*CloudTrail*,*Config*"
                [--exclude <globs>]  # comma-separated globs, e.g. "*us-west-2*,*vpcflowlogs*"
                [--from   <YYYYMMDD>]
                [--to     <YYYYMMDD>]
                [--workers <N>]      # parallel parser threads (default: CPU count; 1 = sequential)
```

DB path resolution order: `--db` CLI arg → `DUCKDB_PATH` env var → `/data/db/threat_hunting.db`.

Date and path filters operate on the filesystem path (CloudTrail stores logs under `yyyy/mm/dd/` segments). Files without a recognizable date segment are always included. `--include`/`--exclude` support `*` crossing path-separator boundaries.

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `OPENAI_API_KEY` | agent only | — |
| `DUCKDB_PATH` | all | — |
| `OPENAI_MODEL` | agent | `gpt-5.4` |
| `OPENAI_MODEL_LITE` | agent | `gpt-5.4-mini` |
| `DUCKDB_HOST_PATH` | docker host | `./data/db` |
| `SUPERSET_SECRET_KEY` | dashboard | `change-me-in-production` |
| `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` | agent (proxy) | — |
| `RAYON_NUM_THREADS` | ingester | CPU count |

