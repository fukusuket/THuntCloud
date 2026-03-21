# ingester

AWS CloudTrail log ingestion module for THuntCloud.

Reads CloudTrail log files (`.json` / `.json.gz`) from the local filesystem, parses them,
and inserts records into DuckDB. This is the **only** component that opens DuckDB in `READ_WRITE` mode.

---

## Quick Start

```bash
# Ingest a directory
ingester ingest --path /logs/cloudtrail/ --db /data/threat_hunting.db

# Date-range filter (January 2024 only)
ingester ingest --path /logs/ --from 20240101 --to 20240131

# Path-pattern filter (CloudTrail logs only, skip a region)
ingester ingest --path /logs/ --include "*CloudTrail*" --exclude "*ap-northeast-3*"

# With GeoIP enrichment
ingester ingest --path /logs/ \
  --geoip-city    /data/geoip/GeoLite2-City.mmdb \
  --geoip-asn     /data/geoip/GeoLite2-ASN.mmdb

# Back-fill GeoIP data on an existing database
ingester enrich \
  --geoip-city /data/geoip/GeoLite2-City.mmdb \
  --geoip-asn  /data/geoip/GeoLite2-ASN.mmdb
```

---

## CLI Reference

```
ingester ingest --path <PATH>
               [--db <PATH>]           DuckDB file (default: /data/db/threat_hunting.db)
               [--from <YYYYMMDD>]     Include files on or after this date
               [--to   <YYYYMMDD>]     Include files on or before this date
               [--include <GLOBS>]     Comma-separated glob patterns to include
               [--exclude <GLOBS>]     Comma-separated glob patterns to exclude
               [--workers <N>]         Parallel parse threads (default: CPU count)
               [--no-progress]         Disable progress bar
               [--geoip-city <PATH>]   GeoLite2-City.mmdb
               [--geoip-country <PATH>] GeoLite2-Country.mmdb
               [--geoip-asn  <PATH>]   GeoLite2-ASN.mmdb

ingester enrich
               [--db <PATH>]
               [--geoip-city / --geoip-country / --geoip-asn <PATH>]
```

`--include`/`--exclude` glob patterns use `*` that crosses `/` boundaries.
Files without a recognisable `yyyy/mm/dd` date segment in their path are always included.

---

## Database Schema

### `cloudtrail_events` (24 columns)

**Core (17):** `event_time`, `event_name`, `event_source`, `aws_region`, `source_ip_address`,
`user_agent`, `user_identity_type`, `user_identity_arn`, `user_identity_account_id`,
`request_parameters`, `response_elements`, `error_code`, `error_message`,
`read_only`, `event_type`, `recipient_account_id`, `raw_event`

**GeoIP (7, nullable):** `geo_country_code`, `geo_country_name`, `geo_city`,
`geo_latitude`, `geo_longitude`, `geo_asn`, `geo_org`

JSON blobs (`request_parameters`, `response_elements`, `raw_event`) are stored as `VARCHAR`.
Use `json_extract_string(column, '$.field')` for ad-hoc queries.

### `ingested_files`

`file_path` (PK), `sha256`, `ingested_at` — tracks ingested files for SHA-256-based deduplication.

---

## Module Structure

```
ingester/
├── Cargo.toml
├── src/
│   ├── main.rs           # CLI entry point (clap)
│   ├── lib.rs            # Public API re-exports
│   ├── parser.rs         # CloudTrail JSON parsing (serde)
│   ├── decompressor.rs   # Transparent gz decompression (flate2)
│   ├── db.rs             # DuckDB schema + batch insert (Appender) + geo backfill
│   ├── ingest.rs         # Pipeline orchestration (rayon parallel → insert)
│   ├── enrich.rs         # Geo back-fill for existing rows
│   ├── geoip.rs          # MaxMind GeoLite2 lookup + private-IP classification
│   ├── date_filter.rs    # --from / --to filter
│   ├── path_filter.rs    # --include / --exclude glob filter
│   └── progress.rs       # Progress bar wrapper (indicatif)
└── tests/
    ├── cli_test.rs
    ├── integration_test.rs
    └── testdata/
```

---

## Development

> **Note:** The `duckdb` crate compiles libduckdb from source. The first build takes 5–10 minutes.

```bash
cd ingester

cargo build                   # Debug build
cargo build --release         # Release build

cargo test                    # All tests (unit + integration + CLI)
cargo test --lib              # Unit tests only
cargo clippy -- -D warnings   # Lint
cargo fmt                     # Format
```
