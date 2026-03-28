# AGENTS.md — THuntCloud

AI coding agent guide for the THuntCloud project.
Module-level detail: [ingester/AGENTS.md](ingester/AGENTS.md) · [agent/AGENTS.md](agent/AGENTS.md)

---

## Architecture at a Glance

Three Docker containers share one DuckDB file via a **bind mount** (`docker/data/db/threat_hunting.db`).

| Container | Language | DuckDB mode | Port |
|-----------|----------|-------------|------|
| `ingester` | Rust 1.85+ | **READ_WRITE** (sole writer) | — |
| `agent` | Python 3.12+ / Streamlit | READ_ONLY | 8501 |
| `dashboard` | Apache Superset | READ_ONLY | 8088 |

The bind-mount (not a named volume) is intentional — Docker Engine on Linux/WSL2 misresolves
relative paths for named-volume `driver_opts`, so each service declares its own `volumes:` entry
in `docker/docker-compose.yml`.

`ingester` must finish before `agent`/`dashboard` start. Concurrent write sessions are not supported.

---

## Development Methodology: TDD

This project strictly follows **Test-Driven Development** (Red-Green-Refactor).

1. Write a test list before coding any feature.
2. Write ONE failing test (Red) — confirm it fails before proceeding.
3. Write the **minimum** code to make it pass (Green).
4. Refactor while keeping all tests green.
5. Repeat for the next item on the test list.

**Never write production code without a corresponding failing test first.**

When implementing a feature:
- Ask: "What is the test list for this feature?"
- Rust: `#[test]` in `#[cfg(test)] mod tests` within the same source file.
- Python: `def test_*` in `agent/tests/test_*.py`.

---

## Coding Conventions

### All modules

- **Language:** All code comments, `///` doc comments, docstrings, commit messages, and PR
  descriptions MUST be written in **English**. No exceptions.
- **Commits:** Conventional Commits — `feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`.
- **Branch naming:** `feature/<module>-<short-desc>` / `fix/<module>-<short-desc>`.

### Rust (`ingester/`)

- **Formatter:** `rustfmt` (default settings) — run `cargo fmt`.
- **Linter:** `clippy` — all warnings must be resolved (`cargo clippy -- -D warnings`).
- **Errors:** `anyhow::Result` everywhere; `.with_context(|| format!("..."))` for context.
- **DB writes:** always use `duckdb::Appender`, never individual `INSERT` statements.
- **Tests:** unit tests in `#[cfg(test)] mod tests` in the same file; integration tests in
  `ingester/tests/`.

### Python (`agent/`)

- **Formatter:** `black` (line length 88).
- **Linter:** `ruff`.
- **Type hints:** required on all function signatures.
- **Docstrings:** Google style.
- **Imports:** stdlib → third-party → local (enforced by `ruff`).
- **OpenAI mocks:** mock as `llm.OpenAI`, **not** `agent.llm.OpenAI`.
  `pytest.ini` sets `pythonpath = .` so modules resolve at the top level.
- **DuckDB in tests:** use `tmp_path / "test.db"` via the `tmp_duckdb` fixture in
  `agent/tests/conftest.py`. Never use a shared file.
- **Real API calls in tests are forbidden** — always mock `llm.OpenAI`.

---

## Essential Commands

Run from `docker/`:

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

Development (run from module directories):

```bash
# Rust (ingester/)
cargo test                    # unit + integration + CLI tests
cargo clippy -- -D warnings   # lint
cargo fmt                     # format

# Python (agent/)
pytest                        # all tests
pytest --cov=. --cov-report=term-missing
ruff check .                  # lint
black .                       # format
```

---

## DuckDB Schema

### `cloudtrail_events` (24 columns)

JSON blobs are stored as **`VARCHAR`**, not DuckDB JSON type.
Use `json_extract_string(column, '$.field')` for ad-hoc queries.

```sql
CREATE TABLE IF NOT EXISTS cloudtrail_events (
    -- Core columns (17)
    event_time               TIMESTAMP,
    event_name               VARCHAR,
    event_source             VARCHAR,
    aws_region               VARCHAR,
    source_ip_address        VARCHAR,
    user_agent               VARCHAR,
    user_identity_type       VARCHAR,
    user_identity_arn        VARCHAR,
    user_identity_account_id VARCHAR,
    request_parameters       VARCHAR,   -- JSON stored as VARCHAR
    response_elements        VARCHAR,   -- JSON stored as VARCHAR
    error_code               VARCHAR,
    error_message            VARCHAR,
    read_only                BOOLEAN,
    event_type               VARCHAR,
    recipient_account_id     VARCHAR,
    raw_event                VARCHAR    -- full original event JSON as VARCHAR
);

-- GeoIP columns (7) — added via ALTER TABLE ADD COLUMN IF NOT EXISTS
-- NULL when ingested without a GeoLite2 database
ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_country_code VARCHAR;
ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_country_name VARCHAR;
ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_city         VARCHAR;
ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_latitude     DOUBLE;
ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_longitude    DOUBLE;
ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_asn          VARCHAR;
ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_org          VARCHAR;
```

### `ingested_files`

`file_path` (PK), `sha256`, `ingested_at` — tracks ingested files for SHA-256-based deduplication.

### DuckDB Access Rules

1. `ingester` is the **sole writer** — never open `READ_WRITE` from `agent` or `dashboard`.
2. `agent` and `dashboard` always use `read_only=True`.
3. Tests must use temporary databases (`tempfile` in Rust, `tmp_path` in pytest).
4. SSD storage is strongly recommended for the DuckDB bind mount.

---

## SQL Safety in `agent/`

Before executing any LLM-generated SQL, `query.py` applies three guards in order:

1. **Keyword blocklist** — rejects `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`
   (regex, word-boundary, case-insensitive).
2. **EXPLAIN validation** — runs `EXPLAIN <sql>` on the READ_ONLY connection.
3. **Row-limit cap** — wraps queries without `LIMIT` in `SELECT * FROM (...) AS _limited LIMIT N`.

If validation fails, `execute_with_retry` calls `fix_sql_with_llm` once for automatic correction.

Date-range UI filters inject a `_ct_filtered` CTE — see `apply_date_filter()` in `agent/query.py`.

`agent/builtin_hunts.yaml` ships pre-built queries with `label`, `description`, `prompt`, and an
optional `sql` field. Entries with `sql` run without an OpenAI API key.

---

## Ingester CLI Reference

```
ingester ingest --path <dir>
                [--db           <path>]     # overrides DUCKDB_PATH env var
                [--from         <YYYYMMDD>]
                [--to           <YYYYMMDD>]
                [--include      <globs>]    # comma-separated, e.g. "*CloudTrail*"
                [--exclude      <globs>]    # comma-separated, e.g. "*us-west-2*"
                [--workers      <N>]        # parallel threads (default: CPU count)
                [--no-progress]
                [--geoip-city   <path>]     # GeoLite2-City.mmdb   (or GEOIP_CITY_PATH)
                [--geoip-country <path>]    # GeoLite2-Country.mmdb (or GEOIP_COUNTRY_PATH)
                [--geoip-asn    <path>]     # GeoLite2-ASN.mmdb    (or GEOIP_ASN_PATH)

ingester enrich
                [--db           <path>]
                [--geoip-city / --geoip-country / --geoip-asn <path>]
```

DB path resolution order: `--db` CLI arg → `DUCKDB_PATH` env var → `/data/db/threat_hunting.db`.

`--include`/`--exclude` globs use `*` that crosses `/` boundaries.
Files without a recognisable `yyyy/mm/dd` segment in their path are always included.

---

## Environment Variables

| Variable | Used by | Default | Notes |
|----------|---------|---------|-------|
| `OPENAI_API_KEY` | agent | — | Required for AI features |
| `DUCKDB_PATH` | all | — | Overrides default DB path |
| `OPENAI_MODEL` | agent | `gpt-5.4` | SQL generation + analysis model |
| `OPENAI_MODEL_LITE` | agent | `gpt-5.4-mini` | Optional lighter model |
| `DUCKDB_HOST_PATH` | docker host | `./data/db` | Host-side bind-mount directory |
| `GEOIP_HOST_PATH` | docker host | `./data/geoip` | Host-side GeoIP directory |
| `GEOIP_CITY_PATH` | ingester | — | Path to GeoLite2-City.mmdb |
| `GEOIP_COUNTRY_PATH` | ingester | — | Path to GeoLite2-Country.mmdb |
| `GEOIP_ASN_PATH` | ingester | — | Path to GeoLite2-ASN.mmdb |
| `SUPERSET_SECRET_KEY` | dashboard | `change-me-in-production` | **Change before exposing to network** |
| `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` | agent | — | CA bundle for corporate TLS proxy |
| `RAYON_NUM_THREADS` | ingester | CPU count | Limits rayon thread pool |

---

## Security Rules

1. **API keys:** never hardcode — always read from environment variables.
2. **SQL safety:** `READ_ONLY` DuckDB connection + keyword blocklist + `EXPLAIN` validation.
3. **No external data upload:** only the OpenAI API call sends data externally (SQL prompt + results).
4. **Network:** all services are local-only by default.

---

## File Structure

```
THuntCloud/
├── .github/
│   ├── AGENTS.md              # Short pointer → see root AGENTS.md
│   └── copilot-instructions.md
├── ingester/                  # Rust log ingestion engine
│   ├── AGENTS.md              # Ingester-specific TDD context
│   ├── README.md
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs            # CLI (ingest + enrich subcommands)
│       ├── lib.rs
│       ├── parser.rs          # CloudTrail JSON parsing (serde_json)
│       ├── db.rs              # DuckDB schema, batch insert (Appender), geo columns
│       ├── ingest.rs          # Pipeline: walk → filter → parallel parse → insert
│       ├── enrich.rs          # Geo back-fill (UPDATE per unique IP)
│       ├── geoip.rs           # MaxMind GeoLite2 lookup + private-IP classification
│       ├── date_filter.rs     # --from / --to path-based date filter
│       ├── path_filter.rs     # --include / --exclude glob filter
│       └── progress.rs        # Progress bar (indicatif)
├── agent/                     # Python / Streamlit AI-agent UI
│   ├── AGENTS.md              # Agent-specific TDD context
│   ├── app.py
│   ├── llm.py
│   ├── query.py
│   ├── report.py
│   ├── schema.py
│   ├── config.py
│   ├── builtin_hunts.yaml
│   └── prompts/system_prompt.py
├── dashboard/                 # Apache Superset BI dashboard
│   ├── Dockerfile
│   ├── superset_config.py
│   ├── assets/                # cloudtrail_default.zip + YAML definitions
│   └── init/                  # bootstrap.sh, register_duckdb.py,
