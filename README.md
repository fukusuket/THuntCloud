# 🪽THuntCloud🪽

## AWS CloudTrail Log Threat Hunting Tool

> SIEM-equivalent AWS CloudTrail threat hunting on a single ordinary laptop — no cloud infrastructure required.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](docker/docker-compose.yml)
[![Rust](https://img.shields.io/badge/rust-1.85%2B-orange.svg)](ingester/Cargo.toml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](agent/requirements.txt)

Drop in your CloudTrail logs, run one command, and start hunting threats immediately.

- **AI-assisted querying** — natural language → SQL via OpenAI API (`gpt-5.4`)
- **GeoIP enrichment** — country, city, and ASN for every source IP via MaxMind GeoLite2
- **Built-in BI dashboard** — Apache Superset with pre-built CloudTrail charts
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

> **Note:** The default build target compiles the ingester from source (Rust + DuckDB C++ bundled).
> The **first build may take 10–30 minutes** depending on your hardware and network speed
> (WSL2 users: ensure Docker Desktop has ≥8 GB RAM allocated).
> Subsequent builds use the Docker layer cache and are much faster.
>
> If you do not need GeoIP enrichment and prefer a fast start, you can use the pre-built binary instead:
> ```bash
> INGESTER_BUILD_TARGET=prebuilt-runtime docker compose --profile ingest run --rm ingester ingest \
>   --path /data/logs
> ```

---

## Common Commands

All commands are run from the `docker/` directory.

```bash
docker compose down && docker compose up -d --build      # Rebuild & restart
docker compose logs -f                                   # View logs
docker compose --profile resync run --rm superset-resync # Fix blank dashboard
```

---

## Modules

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

- [Yamato Security](https://github.com/Yamato-Security) — [suzaku-sample-data](https://github.com/Yamato-Security/suzaku-sample-data)
- [flaws.cloud](http://flaws.cloud) — intentionally vulnerable AWS CloudTrail dataset
- [Apache Superset](https://superset.apache.org/) — BI platform
- [DuckDB](https://duckdb.org/) — embedded analytical database
