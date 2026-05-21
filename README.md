# 🪽THuntCloud🪽

<img src="doc/logo.png" alt="THuntCloud Logo" width="400">

## AWS CloudTrail Log Threat Hunting Tool
> SIEM-equivalent AWS CloudTrail threat hunting on a single ordinary laptop — no cloud infrastructure required.

[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![CI](https://github.com/fukusuket/THuntCloud/actions/workflows/ci.yml/badge.svg)](https://github.com/fukusuket/THuntCloud/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](docker/docker-compose.yml)
[![Rust](https://img.shields.io/badge/rust-1.85%2B-orange.svg)](ingester/Cargo.toml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](agent/requirements.txt)

Drop in your CloudTrail logs, run one command, and start hunting threats immediately.

- **No-query hunting** — select a built-in hunt from the Streamlit dropdown and get instant results — no SQL knowledge required
- **GeoIP enrichment** — country, city, and ASN for every source IP via MaxMind GeoLite2
- **Built-in BI dashboard** — Apache Superset with pre-built CloudTrail charts
- **AWS Config visualization** — interactive resource graph with hierarchical layout (VPC / Subnet / EC2 nesting)
- **Single-command launch** — `docker compose up -d`
- **(Optional) AI-assisted analysis** — AI automatically analyses query result DataFrames and surfaces key findings in plain language

## Screenshots

### Built-in Queries and AI Chat (Streamlit UI) 

<img src="doc/img1.png" width="800" alt="AI Chat UI">

### Built-in Dashboard (Apache Superset)

<img src="doc/img2.png" width="800" alt="Superset Dashboard">

### AWS Config Resource Graph (FastAPI + React)
<img src="doc/img3.png" width="800" alt="AWS Config Resource Graph">
---

## Architecture

Four Docker containers share one DuckDB file via a bind mount (`docker/data/db/`).

```
┌────────────────────────────────────────────────────────────────────────┐
│                             Docker Compose                             │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   ingester   │  │    agent     │  │  config_viz │  │  dashboard  │  │
│  │  (Rust)      │  │  (Streamlit) │  │  (FastAPI+  │  │  (Superset) │  │
│  │              │  │              │  │   React)    │  │             │  │
│  │ CloudTrail   │  │  AI Chat     │  │   Resource  │  │  Visualiz   │  │
│  │ AWS Config   │  │  SQL gen/exec│  │    Graph    │  │             │  │
│  │ ingest       │  │  READ_ONLY   │  │   READ_ONLY │  │   READ_ONLY │  │
│  │ READ_WRITE   │  │              │  │             │  │             │  │
│  └──────┬───────┘  └──────┬───────┘  └────┬────────┘  └─────┬───────┘  │
│         └─────────────────┴───────────────┴─────────────────┘          │
│                                │                                       │
│                         ┌──────▼───────┐                               │
│                         │   DuckDB     │                               │
│                         │ (Bind Mount) │                               │
│                         │   (SSD)      │                               │
│                         └──────────────┘                               │
└────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

| Requirement                           | Details                                            |
|---------------------------------------|----------------------------------------------------|
| **Docker**                            | Docker Desktop or Docker Engine + Compose v2       |
| **Resources**                         | 16 GB RAM minimum, SSD recommended                 |
| **CloudTrail logs**                   | `.json` or `.json.gz` files exported from AWS      |
| *(Optional)* **AWS Config snapshots** | `.json` or `.json.gz` files for AWS resource graph |
| *(Optional)* **OpenAI API key**       | Required for AI query generation                   |
| *(Optional)* **MaxMind GeoLite2**     | `.mmdb` files for GeoIP enrichment                 |

---

## Quick Start

**Step 1.** Download CloudTrail logs from S3.

```bash
aws s3 cp s3://<your-bucket-prefix> <local-output-dir>/ --recursive --include "*.json.gz"
```

**Step 2.** Clone the repository, ingest logs, and start all services.

```bash
# Clone the repository
git clone https://github.com/fukusuket/THuntCloud.git

# Place the downloaded logs into the Docker logs directory
cp -r <local-output-dir>/ THuntCloud/docker/logs/

# Move to the Docker directory
cd THuntCloud/docker

# Ingest CloudTrail logs into DuckDB
docker compose --profile ingest run --rm ingester ingest --path /data/logs --strip-fields --strip-raw-event

# (Optional) Ingest AWS Config snapshots.
docker compose --profile ingest run --rm ingester config-import --path /data/config

# Start all services (agent + dashboard)
docker compose up -d --build
```

**Step 3.** 🪽 Open your browser and start hunting!🪽

- http://localhost:8501 — Built-in queries and AI Chat
- http://localhost:8088 — Dashboard (`admin` / `admin`)
- http://localhost:8502 — AWS Config resource graph


**(Optional)** GeoIP enrichment.
Place [GeoLite2 `.mmdb` files](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) in `docker/data/geoip/`, then:

```bash
docker compose --profile ingest run --rm ingester ingest \
  --path /data/logs \
  --geoip-city /data/geoip/GeoLite2-City.mmdb \
  --geoip-asn  /data/geoip/GeoLite2-ASN.mmdb
```

---

## Corporate Proxy / Custom CA Certificate

If you are behind a TLS-inspecting corporate proxy, see [doc/DEVELOPMENT.md](doc/DEVELOPMENT.md#6-corporate-proxy--custom-ca-certificate) for setup instructions.

---

## Modules

| Module | Language | Role | README |
|--------|----------|------|--------|
| `ingester` | Rust 1.85+ | CloudTrail log ingestion (READ_WRITE) | [ingester/README.md](ingester/README.md) |
| `agent` | Python 3.12+ / Streamlit | AI-assisted interactive chat for threat hunting (READ_ONLY) | [agent/README.md](agent/README.md) |
| `dashboard` | Apache Superset | BI visualization (READ_ONLY) | [dashboard/README.md](dashboard/README.md) |
| `config_viz` | FastAPI + React | AWS Config visualization (READ_ONLY) | [config_viz/README.md](config_viz/README.md) |

---

### End-to-End Sequence Diagram

See [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md#end-to-end-sequence-diagram) for the full lifecycle sequence diagram.

---

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) for details.

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
