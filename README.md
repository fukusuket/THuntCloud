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

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose v2)
- 16 GB RAM minimum, SSD recommended
- OpenAI API key (`gpt-5.4` access)

### 1. Clone and configure

```bash
git clone https://github.com/fukusuket/THuntCloud.git
cd THuntCloud
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

### 2. Place CloudTrail logs

```bash
# Copy your CloudTrail logs (JSON or .gz) into the logs directory
cp /path/to/cloudtrail/logs/*.json.gz docker/logs/
```

### 3. Start agent and dashboard

```bash
cd docker
docker compose up -d
```

### 4. Ingest logs

```bash
# Run from the docker/ directory
docker compose --profile ingest run --rm ingester ingest --path /data/logs
```

### 5. Open the UIs

| Service | URL | Description |
|---------|-----|-------------|
| Agent (AI hunting) | http://localhost:8501 | AI-assisted threat hunting UI |
| Dashboard | http://localhost:8088 | Apache Superset BI dashboard |

Default Superset credentials: `admin` / `admin` (change immediately in production)

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

# View service logs
cd docker && docker compose logs -f agent
cd docker && docker compose logs -f superset

# Stop all services
cd docker && docker compose down
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
