# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2026-03-20

### Added

#### Ingester (Rust)
- CloudTrail log ingestion from local filesystem (`.json` / `.json.gz`)
- Parallel file processing via Rayon with configurable worker count (`--workers`)
- DuckDB storage with 24-column schema (17 core CloudTrail fields + 7 GeoIP enrichment fields)
- SHA-256 deduplication via `ingested_files` table
- GeoIP enrichment using MaxMind GeoLite2 databases (City, Country, ASN) — `ingest` and `enrich` subcommands
- Date-range filtering (`--from` / `--to`) and glob-based path filtering (`--include` / `--exclude`)
- Progress bar output (suppressible with `--no-progress`)
- Pre-built binary release for `x86_64-linux` via GitHub Actions (`release.yml`)
- Pre-built runtime Docker target to skip Rust compilation during `docker compose build`

#### Agent (Python / Streamlit)
- Natural language → SQL query generation via OpenAI API
- AI-assisted threat hunting with built-in query library (`builtin_hunts.yaml`)
- SQL safety guards: keyword blocklist, `EXPLAIN` validation, row-limit cap
- Date-range UI filter with CTE injection
- Automated threat hunting report generation (Markdown)
- READ-ONLY DuckDB connection

#### Dashboard (Apache Superset)
- Pre-seeded CloudTrail dashboards: Events Over Time, Top API Calls, IAM Entity Activity, Error Trends, Top Source IPs
- Docker Compose integration with automatic dashboard import

#### Infrastructure
- Single-command launch via `docker compose up -d`
- CI pipeline: Rust (cargo test + clippy + rustfmt) and Python (pytest + ruff + black)
- Automated GitHub Release workflow triggered on `v*` tags

[0.0.1]: https://github.com/fukusuket/THuntCloud/releases/tag/v0.0.1
