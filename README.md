# 🪽THuntCloud🪽

## AWS CloudTrail Log Threat Hunting Tool

> Locally-executed, AI-assisted threat hunting for AWS CloudTrail logs — no SIEM required.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](docker/docker-compose.yml)
[![Rust](https://img.shields.io/badge/rust-1.85%2B-orange.svg)](ingester/Cargo.toml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](agent/requirements.txt)

## Overview

THuntCloud enables fast, AI-powered threat hunting against AWS CloudTrail logs directly on a local PC.

- **No SIEM required** — all analysis runs locally via DuckDB
- **AI-assisted** — natural language → SQL generation via OpenAI API (`gpt-5.4`)
- **GeoIP enrichment** — enrich `source_ip_address` with country, city, ASN via MaxMind GeoLite2
- **Built-in dashboard** — Apache Superset with pre-seeded CloudTrail dashboards
- **Single-command launch** — `docker compose up -d`

## Screenshots

### AI Agent (Streamlit UI)

<img src="doc/img2.png" width="800" alt="AI Agent UI">

### Dashboard (Apache Superset)

<img src="doc/img1.png" width="800" alt="Superset Dashboard">

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                       │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐  ┌─────────────┐   │
│  │   ingester   │   │    agent     │  │  dashboard  │   │
│  │  (Rust)      │   │  (Streamlit) │  │  (Superset) │   │
│  │              │   │              │  │             │   │
│  │ CloudTrail   │   │  AI-Agent    │  │ BI / Viz    │   │
│  │ gz ingest    │   │ SQL gen/exec │  │             │   │
│  │ READ_WRITE   │   │ READ_ONLY    │  │ READ_ONLY   │   │
│  └──────┬───────┘   └──────┬───────┘  └──────┬──────┘   │
│         └──────────────────┴─────────────────┘          │
│                            │                            │
│                    ┌───────▼──────┐                     │
│                    │   DuckDB     │                     │
│                    │ (Bind Mount) │                     │
│                    │  (SSD)       │                     │
│                    └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose v2)
- 16 GB RAM minimum, SSD recommended
- *(Optional)* OpenAI API key (`gpt-5.4` access) — required for AI query generation
- *(Optional)* [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) `.mmdb` files for GeoIP enrichment

### 1. Clone

```bash
git clone https://github.com/fukusuket/THuntCloud.git
cd THuntCloud
```

### 2. Place CloudTrail logs

```bash
cp /path/to/cloudtrail/logs/*.json.gz docker/logs/
```

### 3. Build and ingest logs

```bash
cd docker
docker compose --profile ingest run --rm ingester ingest --path /data/logs
```

#### With GeoIP enrichment (optional)

Download [GeoLite2 `.mmdb` files](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) and place them in `docker/data/geoip/`, then run:

```bash
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs \
  --geoip-city    /data/geoip/GeoLite2-City.mmdb \
  --geoip-asn     /data/geoip/GeoLite2-ASN.mmdb
```

### 4. Start all services

```bash
docker compose up -d --build
```

### 5. Open the UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| Agent (AI hunting) | http://localhost:8501 | — |
| Dashboard (Superset) | http://localhost:8088 | `admin` / `admin` |

---

## Docker Operations

All commands are run from the `docker/` directory.

```bash
docker compose down && docker compose up -d --build      # Rebuild & restart
docker compose logs -f                                   # View logs
docker compose --profile resync run --rm superset-resync # Fix blank dashboard (re-syncs column metadata)
```

---

## Modules

Each module has its own README with detailed usage and development notes.

| Module | Language | Role | README |
|--------|----------|------|--------|
| `ingester` | Rust | CloudTrail log ingestion (READ_WRITE) | [ingester/README.md](ingester/README.md) |
| `agent` | Python / Streamlit | AI-assisted threat hunting (READ_ONLY) | [agent/README.md](agent/README.md) |
| `dashboard` | Apache Superset | BI visualization (READ_ONLY) | [dashboard/README.md](dashboard/README.md) |

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
See [NOTICE](NOTICE) for third-party license attributions.

## Acknowledgements

- **[Yamato Security](https://github.com/Yamato-Security)** — for providing the [suzaku-sample-data](https://github.com/Yamato-Security/suzaku-sample-data) repository
- **[flaws.cloud](http://flaws.cloud)** — the intentionally vulnerable AWS environment whose CloudTrail logs serve as an excellent threat hunting practice dataset.
- **[Apache Superset](https://superset.apache.org/)** — the open-source BI platform powering the built-in dashboard.
- **[DuckDB](https://duckdb.org/)** — the embedded analytical database at the core of THuntCloud's data engine.
- **[siem-on-amazon-opensearch-service](https://github.com/aws-samples/siem-on-amazon-opensearch-service)** — AWS sample project for SIEM on Amazon OpenSearch Service, referenced for log parsing and normalization patterns.
- **[cloud-trail-lake-query-samples](https://github.com/aws-samples/cloud-trail-lake-query-samples)** — AWS sample queries for CloudTrail Lake, referenced for threat hunting query patterns.
