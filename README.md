# THuntCloud

## AWS Log Threat Hunting Tool

> Locally-executed, AI-assisted threat hunting for AWS CloudTrail logs — no SIEM required.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](docker/docker-compose.yml)

## Overview

This tool enables fast, AI-powered threat hunting against AWS CloudTrail logs directly on a local PC.

- **No SIEM required** — all analysis runs locally via DuckDB
- **AI-assisted** — natural language → SQL generation via OpenAI API (gpt-5.2)
- **High performance** — ingest 10 GB in under 5 minutes; supports 50 GB on 16 GB RAM
- **Built-in dashboard** — Apache Superset with pre-seeded CloudTrail dashboards

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
│  └──────┬───────┘   └──────┬───────┘  └──────┬──────┘  │
│         └──────────────────┴──────────────────┘         │
│                            │                            │
│                    ┌───────▼──────┐                     │
│                    │   DuckDB     │                     │
│                    │  (Persistent │                     │
│                    │   Volume)    │                     │
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
git clone https://github.com/your-org/aws-log-threat-hunting.git
cd aws-log-threat-hunting
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

### 2. Place CloudTrail logs

```bash
# Copy your CloudTrail logs (JSON or .gz) into the data directory
cp /path/to/cloudtrail/logs/*.json.gz data/logs/
```

### 3. Start all services

```bash
docker compose up -d
```

### 4. Ingest logs

```bash
docker compose run --rm ingester ingest --path /data/logs
```

### 5. Open the UIs

| Service | URL | Description |
|---------|-----|-------------|
| Agent (AI hunting) | http://localhost:8501 | AI-assisted threat hunting UI |
| Dashboard | http://localhost:8088 | Apache Superset BI dashboard |

Default Superset credentials: `admin` / `admin` (change immediately)

## Module Overview

| Module | Language / Framework | Role |
|--------|---------------------|------|
| `ingester` | Rust | Parse and load CloudTrail logs into DuckDB |
| `agent` | Python / Streamlit | AI-Agent UI for interactive threat hunting |
| `dashboard` | Apache Superset | BI visualization of log data |

## Directory Structure

```
THuntCloud/
├── ingester/          # Rust log ingestion engine
├── agent/             # Streamlit AI-Agent UI
├── dashboard/         # Superset seeding and config
├── dashboards/        # Pre-built dashboard definitions (ZIP/YAML)
├── data/              # Log data directory (git-ignored)
├── docker/            # Docker Compose and Dockerfiles
├── docs/              # Documentation
└── .env.example       # Environment variable template
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
See [NOTICE](NOTICE) for third-party license attributions.
