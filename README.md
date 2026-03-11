# THuntCloud

## AWS Log Threat Hunting Tool

> Locally-executed, AI-assisted threat hunting for AWS CloudTrail logs — no SIEM required.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](docker/docker-compose.yml)
[![Rust](https://img.shields.io/badge/rust-1.85%2B-orange.svg)](ingester/Cargo.toml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](agent/requirements.txt)

## Overview

THuntCloud enables fast, AI-powered threat hunting against AWS CloudTrail logs directly on a local PC.

- **No SIEM required** — all analysis runs locally via DuckDB
- **AI-assisted** — natural language → SQL generation via OpenAI API (`gpt-5.4`)
- **High performance** — ingest 10 GB in under 5 minutes; supports 50 GB on 16 GB RAM
- **Built-in dashboard** — Apache Superset with pre-seeded CloudTrail dashboards
- **Single-command launch** — `docker compose up -d`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐  ┌─────────────┐  │
│  │   ingester   │   │    agent     │  │  dashboard  │  │
│  │  (Rust)      │   │  (Streamlit) │  │  (Superset) │  │
│  │              │   │              │  │             │  │
│  │ CloudTrail   │   │  AI-Agent    │  │ BI / Viz    │  │
│  │ gz ingest    │   │ SQL gen/exec │  │             │  │
│  │ READ_WRITE   │   │ READ_ONLY    │  │ READ_ONLY   │  │
│  └──────┬───────┘   └──────┬───────┘  └──────┬──────┘  │
│         └──────────────────┴──────────────────┘         │
│                            │                            │
│                    ┌───────▼──────┐                     │
│                    │   DuckDB     │                     │
│                    │  (Named Vol) │                     │
│                    │  (SSD)       │                     │
│                    └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

## Quick Start with Sample Data

The fastest way to try THuntCloud is to use the publicly available CloudTrail sample logs from [Yamato Security's suzaku-sample-data](https://github.com/Yamato-Security/suzaku-sample-data).

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose v2)
- 16 GB RAM minimum, SSD recommended
- OpenAI API key (`gpt-5.4` access) — agent module requires this
- `git` with Git LFS support (sample data uses Git LFS)

### 1. Clone THuntCloud and configure

```bash
git clone https://github.com/fukusuket/THuntCloud.git
cd THuntCloud
export OPENAI_API_KEY="sk-..."   # Set your OpenAI API key
```

### 2. Download sample CloudTrail logs

Clone the sample data repository (requires [Git LFS](https://git-lfs.com/)):

```bash
# Install Git LFS if not already installed (macOS)
brew install git-lfs
git lfs install

# Clone only the AWS sample logs (sparse checkout to save disk space)
git clone --no-checkout --depth=1 https://github.com/Yamato-Security/suzaku-sample-data.git
cd suzaku-sample-data
git sparse-checkout init --cone
git sparse-checkout set aws/flaws.cloud
git checkout main
cd ..

# Copy the sample logs into the THuntCloud logs directory
cp suzaku-sample-data/aws/flaws.cloud/*.json.gz docker/logs/
```

> **About the sample data:** The `flaws.cloud` dataset contains CloudTrail logs from the [flaws.cloud](http://flaws.cloud) intentionally vulnerable AWS environment — a great dataset for practising threat hunting.

### 3. Build and ingest logs

```bash
cd docker

# Build the ingester image
docker compose --profile ingest build ingester

# Run ingestion (creates DuckDB and loads all log files)
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs
```

### 4. Start all services (dashboard + agent)

```bash
# (still inside docker/)
docker compose up -d --build
```

This starts:
- **superset-init** — one-shot initializer (DB migration, DuckDB/dataset registration, dashboard import)
- **superset (dashboard)** — Apache Superset BI dashboard
- **agent** — Streamlit AI-assisted threat hunting UI

### 5. Open the UIs

| Service | URL | Description |
|---------|-----|-------------|
| Agent (AI hunting) | http://localhost:8501 | AI-assisted threat hunting UI |
| Dashboard | http://localhost:8088 | Apache Superset BI dashboard |

Default Superset credentials: `admin` / `admin` (change immediately in production)

### Example queries to try

Once the agent is running, try asking questions like:

- `"Who accessed the S3 buckets and from which IP addresses?"`
- `"Show me all IAM-related API calls ordered by time"`
- `"List any failed authentication attempts"`

---

## Quick Start (with your own logs)

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose v2)
- 16 GB RAM minimum, SSD recommended
- OpenAI API key (`gpt-5.4` access) — agent module requires this

### 1. Clone and configure

```bash
git clone https://github.com/fukusuket/THuntCloud.git
cd THuntCloud
export OPENAI_API_KEY="sk-..."   # Set your OpenAI API key
```

### 2. Place CloudTrail logs

```bash
# Copy your CloudTrail logs (JSON or .gz) into the logs directory
cp /path/to/cloudtrail/logs/*.json.gz docker/logs/
```

### 3. Build and ingest logs

```bash
cd docker

# Build the ingester image
docker compose --profile ingest build ingester

# Run ingestion (creates DuckDB and loads all log files)
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs
```

### 4. Start all services (dashboard + agent)

```bash
cd docker

# Build and start Superset dashboard + AI agent
docker compose up -d --build
```

This starts:
- **superset-init** — one-shot initializer (DB migration, DuckDB/dataset registration, dashboard import)
- **superset (dashboard)** — Apache Superset BI dashboard
- **agent** — Streamlit AI-assisted threat hunting UI

### 5. Open the UIs

| Service | URL | Description |
|---------|-----|-------------|
| Agent (AI hunting) | http://localhost:8501 | AI-assisted threat hunting UI |
| Dashboard | http://localhost:8088 | Apache Superset BI dashboard |

Default Superset credentials: `admin` / `admin` (change immediately in production)

---

## Docker Operations

All commands are run from the `docker/` directory:

```bash
cd docker
```

### Clean Start (from scratch)

```bash
# 1. Stop all containers and remove volumes
docker compose down -v
rm -f data/db/threat_hunting.db data/db/threat_hunting.db.wal

# 2. Build and run ingester
docker compose --profile ingest build ingester
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs

# 3. Build and start dashboard + agent
docker compose up -d --build
```

### Restart (keep data)

```bash
# Stop and restart all services (DuckDB data is preserved)
docker compose down
docker compose up -d
```

### Rebuild and Restart (after code changes)

```bash
# Rebuild images and restart
docker compose down
docker compose up -d --build
```

### Start Individual Services

```bash
# Dashboard only (no agent)
docker compose up -d superset

# Agent only (no dashboard)
docker compose up -d agent

# Both
docker compose up -d
```

### Re-ingest Logs

```bash
# Stop readers first to avoid DuckDB lock conflicts
docker compose down

# Clean old data
rm -f data/db/threat_hunting.db data/db/threat_hunting.db.wal

# Re-ingest
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs

# Restart services
docker compose up -d --build
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f superset
docker compose logs -f agent
docker compose logs superset-init    # init is one-shot, no -f needed
```

### Stop All Services

```bash
docker compose down        # stop containers (keep data)
docker compose down -v     # stop containers AND delete volumes (full reset)
```

## Module Overview

| Module | Language / Framework | Role |
|--------|---------------------|------|
| `ingester` | Rust 1.85+ | Parse and load CloudTrail logs into DuckDB (READ_WRITE) |
| `agent` | Python 3.12+ / Streamlit | AI-Agent UI for interactive threat hunting (READ_ONLY) |
| `dashboard` | Apache Superset | BI visualization of log data (READ_ONLY) |

## Environment Variables

| Variable | Module | Default | Description |
|----------|--------|---------|-------------|
| `OPENAI_API_KEY` | agent | *(required)* | OpenAI API key |
| `OPENAI_MODEL` | agent | `gpt-5.4` | Primary AI model for SQL generation |
| `OPENAI_MODEL_LITE` | agent | `gpt-5.4-mini` | Lightweight model for quick tasks |
| `DUCKDB_PATH` | all | *(required)* | Path to DuckDB file inside container |
| `DUCKDB_READONLY` | agent | `true` | Force read-only mode |
| `RUST_LOG` | ingester | `info` | Rust log level (`trace`, `debug`, `info`, `warn`, `error`) |
| `SUPERSET_SECRET_KEY` | dashboard | `change-me-in-production` | Superset secret key |
| `SUPERSET_ADMIN_USERNAME` | dashboard | `admin` | Superset admin username |
| `SUPERSET_ADMIN_PASSWORD` | dashboard | `admin` | Superset admin password |
| `DUCKDB_HOST_PATH` | docker | `./data/db` | Host path for DuckDB volume bind (SSD recommended) |

## Directory Structure

```
THuntCloud/
├── .github/           # Copilot agent instructions & CI workflows
├── ingester/          # Rust log ingestion engine (READ_WRITE)
│   ├── src/           # Parser, decompressor, DuckDB writer, CLI
│   └── tests/         # Integration tests & test data
├── agent/             # Streamlit AI-Agent UI (READ_ONLY)
│   ├── prompts/       # System prompt templates
│   └── tests/         # pytest unit tests
├── dashboard/         # Superset config & bootstrap scripts
├── dashboards/        # Pre-built dashboard definitions (ZIP/YAML)
├── data/              # Log data directory (git-ignored)
├── docker/            # Docker Compose entry point
│   ├── docker-compose.yml
│   ├── data/db/       # DuckDB persistent volume (bind mount)
│   └── logs/          # Source log directory (mount into ingester)
├── doc/               # Documentation (PRD, Architecture, TDD guide, etc.)
├── .env.example       # Environment variable template
├── LICENSE            # Apache License 2.0
└── NOTICE             # Third-party license attributions
```

## Development

### Requirements

| Tool | Version | Purpose |
|------|---------|---------|
| Rust | 1.85+ | ingester development |
| Python | 3.12+ | agent development |
| Docker Desktop | Latest | Container orchestration |
| Docker Compose | v2 | Multi-service management |
| DuckDB CLI | 1.2+ | Ad-hoc database inspection (optional) |

### ingester (Rust)

```bash
cd ingester
cargo build
cargo test
cargo clippy -- -D warnings
cargo fmt --check
```

### agent (Python)

```bash
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
ruff check .
black --check .
```

### Useful Commands

```bash
# Inspect DuckDB directly
duckdb docker/data/db/threat_hunting.db "SELECT COUNT(*) FROM cloudtrail_events"

# Check container status
cd docker && docker ps --filter "name=threat-hunting" --format "table {{.Names}}\t{{.Status}}"
```

## Documentation

| Document | Description |
|----------|-------------|
| [doc/PRD.md](doc/PRD.md) | Product Requirements Document |
| [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) | System architecture |
| [doc/DEVELOPMENT.md](doc/DEVELOPMENT.md) | Development setup guide |
| [doc/TDD_GUIDE.md](doc/TDD_GUIDE.md) | TDD methodology and examples |
| [doc/TESTING.md](doc/TESTING.md) | Testing strategy per module |

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
See [NOTICE](NOTICE) for third-party license attributions.

## Acknowledgements

- **[Yamato Security](https://github.com/Yamato-Security)** — for providing the [suzaku-sample-data](https://github.com/Yamato-Security/suzaku-sample-data) repository, which includes the `flaws.cloud` CloudTrail sample logs used in the Quick Start guide.
- **[flaws.cloud](http://flaws.cloud)** — the intentionally vulnerable AWS environment whose CloudTrail logs serve as an excellent threat hunting practice dataset.
- **[Apache Superset](https://superset.apache.org/)** — the open-source BI platform powering the built-in dashboard.
- **[DuckDB](https://duckdb.org/)** — the embedded analytical database at the core of THuntCloud's data engine.

