# 🪽THuntCloud🪽

## AWS CloudTrail Log Threat Hunting Tool

> SIEM-equivalent AWS CloudTrail threat hunting on a single ordinary laptop — no cloud infrastructure required.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/fukusuket/THuntCloud/actions/workflows/ci.yml/badge.svg)](https://github.com/fukusuket/THuntCloud/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](docker/docker-compose.yml)
[![Rust](https://img.shields.io/badge/rust-1.85%2B-orange.svg)](ingester/Cargo.toml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](agent/requirements.txt)

Drop in your CloudTrail logs, run one command, and start hunting threats immediately.

- **No-query hunting** — select a built-in hunt from the Streamlit dropdown and get instant results — no SQL knowledge required
- **AI-assisted analysis** — OpenAI API (`gpt-5.4`) automatically analyses query result DataFrames and surfaces key findings in plain language
- **GeoIP enrichment** — country, city, and ASN for every source IP via MaxMind GeoLite2
- **Built-in BI dashboard** — Apache Superset with pre-built CloudTrail charts
- **Single-command launch** — `docker compose up -d`

## Screenshots

### AI Agent (Streamlit UI)

<img src="doc/img1.png" width="800" alt="AI Agent UI">

### Dashboard (Apache Superset)

<img src="doc/img2.png" width="800" alt="Superset Dashboard">

---

## Architecture

Three Docker containers share one DuckDB file via a bind mount (`docker/data/db/`).

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                       │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐  ┌─────────────┐   │
│  │   ingester   │   │    agent     │  │  dashboard  │   │
│  │  (Rust)      │   │  (Streamlit) │  │  (Superset) │   │
│  │              │   │              │  │             │   │
│  │ CloudTrail   │   │  AI-Agent    │  │  Visualize  │   │
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

### End-to-End Sequence Diagram

The diagram below shows the full lifecycle from log ingestion through to a
completed AI-assisted threat hunting session.

```mermaid
sequenceDiagram
    participant OPS  as Operator
    participant ING  as ingester (Rust)
    participant DB   as DuckDB (bind mount)
    participant APP  as agent / Streamlit
    participant OAI  as OpenAI API
    participant SS   as dashboard / Superset
    participant U    as Analyst (Browser)

    Note over OPS,ING: Phase 1 — Ingest
    OPS->>ING: docker compose run ingester ingest --path /data/logs
    ING->>ING: walk & filter files (date, path glob)
    ING->>ING: parallel parse (rayon) + SHA-256 dedup
    ING->>DB: batch insert via DuckDB Appender (READ_WRITE)
    ING->>DB: GeoIP enrich (optional)
    ING-->>OPS: IngestStats printed

    Note over OPS,SS: Phase 2 — Start services
    OPS->>APP: docker compose up -d
    OPS->>SS: docker compose up -d
    APP->>DB: open READ_ONLY connection
    SS->>DB: open READ_ONLY connection

    Note over U,OAI: Phase 3 — AI-assisted hunting (agent)
    U->>APP: natural language question
    APP->>OAI: generate_sql(question, schema, history)
    OAI-->>APP: SQL string
    APP->>APP: apply_date_filter + apply_row_limit
    APP->>APP: validate_query (blocklist + EXPLAIN)
    APP->>DB: execute SQL (READ_ONLY)
    DB-->>APP: result rows (DataFrame)
    APP->>OAI: generate_analysis(sql, results)
    OAI-->>APP: fact-based Markdown summary
    APP-->>U: table + analysis + chat history

    Note over U,SS: Phase 4 — BI dashboard (Superset)
    U->>SS: open http://localhost:8088
    SS->>DB: execute chart queries (READ_ONLY)
    DB-->>SS: aggregated result sets
    SS-->>U: interactive charts + filters
```

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Docker** | Docker Desktop or Docker Engine + Compose v2 |
| **Resources** | 16 GB RAM minimum, SSD recommended |
| **CloudTrail logs** | `.json` or `.json.gz` files exported from AWS |
| *(Optional)* **OpenAI API key** | Required for AI query generation |
| *(Optional)* **MaxMind GeoLite2** | `.mmdb` files for GeoIP enrichment |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/fukusuket/THuntCloud.git
cd THuntCloud/docker

# 2. Place CloudTrail logs
cp /path/to/cloudtrail/logs/*.json.gz logs/

# 3. Ingest logs
docker compose --profile ingest run --rm ingester ingest --path /data/logs

# 4. Start all services
docker compose up -d --build
```

Open http://localhost:8501 (Agent) or http://localhost:8088 (Dashboard, `admin`/`admin`).

#### With GeoIP enrichment (optional)

Place [GeoLite2 `.mmdb` files](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) in `docker/data/geoip/`, then:

```bash
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs \
  --geoip-city /data/geoip/GeoLite2-City.mmdb \
  --geoip-asn  /data/geoip/GeoLite2-ASN.mmdb
```

---

## Common Commands

All commands are run from the `docker/` directory.

```bash
docker compose down && docker compose up -d --build      # Rebuild & restart
docker compose logs -f                                   # View logs
docker compose --profile resync run --rm superset-resync # Fix blank dashboard after re-ingest
```

---

## Modules

| Module | Language | Role | README |
|--------|----------|------|--------|
| `ingester` | Rust 1.85+ | CloudTrail log ingestion (READ_WRITE) | [ingester/README.md](ingester/README.md) |
| `agent` | Python 3.12+ / Streamlit | AI-assisted threat hunting (READ_ONLY) | [agent/README.md](agent/README.md) |
| `dashboard` | Apache Superset | BI visualization (READ_ONLY) | [dashboard/README.md](dashboard/README.md) |

---

## CI

The CI pipeline runs on every push / pull request to `main` and `develop`.

| Job | Checks |
|-----|--------|
| `ingester (Rust)` | `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test --all` |
| `agent (Python)` | `black --check`, `ruff check`, `pytest -v` |
| `dashboard YAML validation` | All dashboard YAML files are well-formed; ZIP contains required files |

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
See [NOTICE](NOTICE) for third-party license attributions.

## Acknowledgements

This project exists thanks to these wonderful projects and datasets :)

- [Yamato Security](https://github.com/Yamato-Security) — [suzaku-sample-data](https://github.com/Yamato-Security/suzaku-sample-data)
- [Suzaku](https://github.com/Yamato-Security/suzaku) — Suzaku, a CloudTrail log analysis tool created by Yamato Security
- [flaws.cloud](http://flaws.cloud) — intentionally vulnerable AWS CloudTrail dataset
- [Apache Superset](https://superset.apache.org/) — BI platform
- [DuckDB](https://duckdb.org/) — embedded analytical database
- [SIEM on Amazon OpenSearch Service](https://github.com/aws-samples/siem-on-amazon-opensearch-service) — SIEM-like CloudTrail analytics reference implementation
- [AWS CloudTrail Lake query samples](https://github.com/aws-samples/cloud-trail-lake-query-samples) — CloudTrail Lake query examples
- [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) — GeoIP databases
