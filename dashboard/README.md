# dashboard

BI dashboard module for THuntCloud powered by Apache Superset.
Visualizes CloudTrail log data stored in DuckDB. Always opens DuckDB in **`READ_ONLY`** mode.

---

## Quick Start

```bash
# Run from docker/

# 1. (First time) Ingest logs
docker compose --profile ingest run --rm ingester ingest --path /data/logs

# 2. Start the dashboard
docker compose up -d superset
```

Open http://localhost:8088 (default credentials: `admin` / `admin`).

---

## Configuration

| Variable                  | Default                    | Description                       |
|---------------------------|----------------------------|-----------------------------------|
| `SUPERSET_SECRET_KEY`     | `change-me-in-production`  | Session signing key (**change!**) |
| `SUPERSET_ADMIN_USERNAME` | `admin`                    | Admin username                    |
| `SUPERSET_ADMIN_PASSWORD` | `admin`                    | Admin password (**change!**)      |
| `DUCKDB_PATH`             | `/data/db/threat_hunting.db` | DuckDB file path (in container) |
| `DUCKDB_HOST_PATH`        | `./data/db`                | Host-side DuckDB directory        |

---

## Initialization

On first startup `superset-init` runs automatically (idempotent):

1. `superset db upgrade` — run metadata DB migrations
2. `superset fab create-admin` — create admin user
3. `superset init` — initialize roles and permissions
4. `register_duckdb.py` — register DuckDB connection (READ_ONLY)
5. `register_dataset.py` — register `cloudtrail_events` dataset
6. `import_dashboards` — import pre-built CloudTrail dashboards

The `superset` service starts only after `superset-init` exits successfully.

---

## Directory Structure

```
dashboard/
├── Dockerfile               # Extends apache/superset:4.1.2 with duckdb-engine
├── superset_config.py
├── assets/
│   ├── cloudtrail_default.zip        # Superset import ZIP
│   ├── rebuild_zip.py
│   └── cloudtrail_default/           # Dashboard definitions (Superset export format)
└── init/
    ├── bootstrap.sh
    ├── register_duckdb.py
    ├── register_dataset.py
    └── import_dashboard.py
```

---

## Development

```bash
cd docker

# Build the custom image
docker compose build superset

# Verify duckdb-engine is installed
docker compose run --rm superset python -c "import duckdb_engine; print('OK')"

# Re-run initialization (safe — idempotent)
docker compose run --rm superset-init

# Fix blank dashboard after re-ingest (re-syncs column metadata)
docker compose --profile resync run --rm superset-resync
```