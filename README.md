# 🪽THuntCloud🪽

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

## Processing Sequence

For detailed processing flow diagrams, see each module's documentation:

- [ingester — Log Ingestion Flow](ingester/README.md#processing-sequence)
- [agent — AI-Assisted Threat Hunting Flow](agent/README.md#processing-sequence)
- [dashboard — Dashboard Visualization Flow](dashboard/README.md#processing-sequence)

---

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose v2)
- 16 GB RAM minimum, SSD recommended
- *(Optional)* OpenAI API key (`gpt-5.4` access) — agent module requires this
- *(Optional)* [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) `.mmdb` files for GeoIP enrichment

### 1. Clone

```bash
git clone https://github.com/fukusuket/THuntCloud.git
cd THuntCloud
```

### 2. Place CloudTrail logs

```bash
# Your own logs
cp /path/to/cloudtrail/logs/*.json.gz docker/logs/
```

### 3. Build and ingest logs

```bash
cd docker
docker compose --profile ingest build ingester
docker compose --profile ingest run --rm ingester ingest --path /data/logs
```

#### Using a pre-built ingester binary (faster)

If you are on **x86_64 Linux** (or WSL2 / Docker Desktop on amd64), you can skip
the Rust + DuckDB C++ compilation step by downloading a pre-built binary from a
[GitHub Release](https://github.com/fukusuket/THuntCloud/releases):

```bash
cd docker
# Replace v0.1.3 with the latest release tag
INGESTER_VERSION=v0.1.3 INGESTER_BUILD_TARGET=prebuilt-runtime \
  docker compose --profile ingest build ingester
docker compose --profile ingest run --rm ingester ingest --path /data/logs
```

#### With GeoIP enrichment (optional)

Download [GeoLite2 `.mmdb` files](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) and place them in `docker/data/geoip/`.

```
docker/
└── data/
    └── geoip/                        ← place .mmdb files here
        ├── GeoLite2-City.mmdb
        ├── GeoLite2-Country.mmdb
        └── GeoLite2-ASN.mmdb
```

These files are bind-mounted read-only into the container at `/data/geoip/`.  
Three database types are supported:

| Flag | Database | Provides |
|------|----------|----------|
| `--geoip-city` | GeoLite2-City.mmdb | Country + city + lat/lon |
| `--geoip-country` | GeoLite2-Country.mmdb | Country only (lighter alternative to City) |
| `--geoip-asn` | GeoLite2-ASN.mmdb | ASN number + organization name |

**Full enrichment (City + ASN):**

```bash
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs \
  --geoip-city /data/geoip/GeoLite2-City.mmdb \
  --geoip-asn  /data/geoip/GeoLite2-ASN.mmdb
```


```bash
docker compose --profile ingest run --rm ingester ingest --path /data/logs
```

#### Back-fill GeoIP on an existing database

If logs were already ingested without GeoIP, use the `enrich` subcommand to back-fill the geo columns without re-ingesting.  
Place `.mmdb` files in `docker/data/geoip/` first, then:

```bash
# Full enrichment (City + ASN)
docker compose --profile ingest run --rm ingester enrich \
  --geoip-city /data/geoip/GeoLite2-City.mmdb \
  --geoip-asn  /data/geoip/GeoLite2-ASN.mmdb

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
docker compose down && docker compose up -d              # Restart (keep data)
docker compose down && docker compose up -d --build      # Rebuild & restart
docker compose up -d superset                            # Dashboard only
docker compose up -d agent                               # Agent only
docker compose logs -f                                   # View logs
docker compose down -v                                   # Full reset (delete data)
docker compose --profile resync run --rm superset-resync # Fix blank dashboard (re-syncs column metadata)
```

### Re-ingest Logs

```bash
docker compose down
rm -f data/db/threat_hunting.db data/db/threat_hunting.db.wal
docker compose --profile ingest run --rm ingester ingest --path /data/logs
docker compose up -d --build
docker compose --profile resync run --rm superset-resync  # Re-sync dashboard column metadata
```

---

## ingester CLI Reference

```
ingester ingest --path <dir>
                [--db             <path>]    # DuckDB file (default: /data/db/threat_hunting.db)
                [--no-progress]              # Disable progress bar output
                [--include        <globs>]   # comma-separated include patterns, e.g. "*CloudTrail*"
                [--exclude        <globs>]   # comma-separated exclude patterns, e.g. "*vpcflowlogs*"
                [--from           <YYYYMMDD>]# ingest files on or after this date
                [--to             <YYYYMMDD>]# ingest files on or before this date
                [--workers        <N>]       # parallel threads (default: CPU count)
                [--geoip-city     <path>]    # GeoLite2-City.mmdb    (or GEOIP_CITY_PATH env)
                [--geoip-country  <path>]    # GeoLite2-Country.mmdb (or GEOIP_COUNTRY_PATH env)
                [--geoip-asn      <path>]    # GeoLite2-ASN.mmdb     (or GEOIP_ASN_PATH env)

ingester enrich
                [--db             <path>]    # DuckDB file (default: /data/db/threat_hunting.db)
                [--geoip-city     <path>]    # GeoLite2-City.mmdb    (or GEOIP_CITY_PATH env)
                [--geoip-country  <path>]    # GeoLite2-Country.mmdb (or GEOIP_COUNTRY_PATH env)
                [--geoip-asn      <path>]    # GeoLite2-ASN.mmdb     (or GEOIP_ASN_PATH env)
```
---

## Module Overview

| Module | Language / Framework | Role |
|--------|---------------------|------|
| `ingester` | Rust 1.85+ | Parse and load CloudTrail logs into DuckDB; optional GeoIP enrichment (READ_WRITE) |
| `agent` | Python 3.12+ / Streamlit | AI-Agent UI for interactive threat hunting (READ_ONLY) |
| `dashboard` | Apache Superset | BI visualization of log data (READ_ONLY) |

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
