# ingester

AWS CloudTrail log ingestion module for THuntCloud.

Reads CloudTrail log files (`.json` / `.json.gz`) from the local filesystem,
parses them, and inserts the records into a DuckDB database. This is the
**only** component in THuntCloud that opens DuckDB in `READ_WRITE` mode.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Output Format](#output-format)
- [Database Schema](#database-schema)
- [Module Structure](#module-structure)
- [Public API](#public-api)
- [Development](#development)
  - [Prerequisites](#prerequisites)
  - [Build](#build)
  - [Test](#test)
  - [Lint & Format](#lint--format)
- [Architecture Notes](#architecture-notes)

---

## Features

| ID     | Feature                                          | Status |
|--------|--------------------------------------------------|--------|
| ING-01 | CloudTrail JSON log file ingestion               | ✅ |
| ING-02 | Transparent `.json.gz` decompression             | ✅ |
| ING-03 | Recursive directory walk and batch ingestion     | ✅ |
| ING-04 | Automatic schema creation in DuckDB              | ✅ |
| ING-05 | Console progress bar (file count, record count)  | ✅ |
| ING-06 | Duplicate prevention via SHA-256 checksum        | ✅ |
| ING-07 | Per-file error logging (skipped files reported)  | ✅ |
| ING-08 | Date-range filter (`--from` / `--to`)            | ✅ |
| ING-09 | Path-pattern filter (`--include` / `--exclude`)  | ✅ |
| ING-10 | GeoIP enrichment via MaxMind GeoLite2 (ingest)   | ✅ |
| ING-11 | GeoIP back-fill for existing DB (`enrich`)       | ✅ |
| ING-12 | Parallel file parsing with rayon (`--workers`)   | ✅ |

---

## Quick Start

```bash
# Ingest a single file
ingester ingest --path /logs/cloudtrail/my-log.json.gz --db /data/threat_hunting.db

# Ingest an entire directory tree
ingester ingest --path /logs/cloudtrail/ --db /data/threat_hunting.db

# Use the default DB path (/data/threat_hunting.db)
ingester ingest --path /logs/cloudtrail/

# Ingest only January 2024 logs (date-range filter)
ingester ingest --path /logs/ --from 20240101 --to 20240131

# Ingest only CloudTrail logs from a mixed-service S3 bucket (path-pattern filter)
ingester ingest --path /logs/ --include "*CloudTrail*"

# Combine both filters: CloudTrail logs in a specific month, excluding a region
ingester ingest --path /logs/ \
  --from 20240101 --to 20240131 \
  --include "*CloudTrail*" \
  --exclude "*ap-northeast-3*"
```

---

## CLI Reference

```
ingester ingest [OPTIONS] --path <PATH>

Options:
  -p, --path <PATH>           Path to a CloudTrail log file or directory [required]
  -d, --db   <DB_PATH>        Path to the DuckDB database file
                              [default: /data/threat_hunting.db]
      --no-progress           Disable the progress bar
      --from <YYYYMMDD>       Include only files on or after this date
      --to   <YYYYMMDD>       Include only files on or before this date
      --include <PATTERNS>    Include only files whose path matches these
                              comma-separated glob patterns (e.g. *CloudTrail*)
      --exclude <PATTERNS>    Exclude files whose path matches these
                              comma-separated glob patterns (e.g. *Config*)
      --workers <N>           Number of parallel parse threads
                              [default: number of logical CPU cores]
                              Set to 1 to minimise peak memory usage
  -h, --help                  Print help
  -V, --version               Print version
```

### Date-range filter (`--from` / `--to`)

CloudTrail exports logs to S3 under a `yyyy/mm/dd/` directory structure.
The `--from` and `--to` options compare the `yyyy/mm/dd` segment found in each
file's path against the specified date range (inclusive on both ends).

- Format: `YYYYMMDD` (e.g. `20240115`)
- Files whose path contains **no** recognisable date segment are always included
  (conservative: unclassifiable files are never silently dropped).

```bash
# January 2024 only
ingester ingest --path /logs/ --from 20240101 --to 20240131

# Everything from a specific day onwards
ingester ingest --path /logs/ --from 20240601
```

### Path-pattern filter (`--include` / `--exclude`)

S3 buckets often store logs from multiple AWS services (CloudTrail, Config,
VPC Flow Logs, ALB, …) under the same prefix. The `--include` and `--exclude`
options filter by the full file path using shell-style glob patterns.

- The `*` wildcard crosses `/` boundaries, so `*CloudTrail*` matches anywhere
  in the full path.
- Multiple patterns are separated by commas (OR logic within the same option).
- `--exclude` is evaluated after `--include`; an exclude match always wins.

| `--include` | `--exclude` | Result |
|-------------|-------------|--------|
| not set     | not set     | all files |
| set         | not set     | files matching ≥ 1 include pattern |
| not set     | set         | files matching no exclude pattern |
| set         | set         | must satisfy both conditions |

```bash
# CloudTrail logs only
ingester ingest --path /logs/ --include "*CloudTrail*"

# CloudTrail and Config, but skip us-west-2
ingester ingest --path /logs/ \
  --include "*CloudTrail*,*Config*" \
  --exclude "*us-west-2*"
```

### Supported file types

| Extension     | Handling                              |
|---------------|---------------------------------------|
| `.json`       | Read directly                         |
| `.json.gz`    | Decompressed on the fly via `flate2`  |
| Anything else | Silently skipped                      |

---

## Output Format

On success the binary prints a single summary line to stdout:

```
Ingestion complete: files_processed=42 records_inserted=158432 errors=0 elapsed_secs=12.34
```

Errors are written to stderr, one line per failed file:

```
Error ingesting /logs/bad-file.json: Failed to parse CloudTrail log JSON: ...
```

Exit codes:

| Code | Meaning                                      |
|------|----------------------------------------------|
| `0`  | Completed (individual file errors are logged but do not affect the exit code) |
| `1`  | Fatal error (e.g. could not open DuckDB, invalid `--path`) |

---

## Database Schema

The ingester creates two tables on first run (both are idempotent):

### `cloudtrail_events`

Stores every ingested CloudTrail event record. **24 columns total** (17 core + 7 GeoIP enrichment).

| Column                    | Type        | Notes                                               |
|---------------------------|-------------|-----------------------------------------------------|
| `event_time`              | `TIMESTAMP` | Auto-cast from ISO-8601 string                      |
| `event_name`              | `VARCHAR`   |                                                     |
| `event_source`            | `VARCHAR`   |                                                     |
| `aws_region`              | `VARCHAR`   |                                                     |
| `source_ip_address`       | `VARCHAR`   | Nullable                                            |
| `user_agent`              | `VARCHAR`   | Nullable                                            |
| `user_identity_type`      | `VARCHAR`   | Expanded from `userIdentity.type`; nullable         |
| `user_identity_arn`       | `VARCHAR`   | Expanded from `userIdentity.arn`; nullable          |
| `user_identity_account_id`| `VARCHAR`   | Expanded from `userIdentity.accountId`; nullable    |
| `request_parameters`      | `VARCHAR`   | Full JSON blob as VARCHAR; use `json_extract_string()` |
| `response_elements`       | `VARCHAR`   | Full JSON blob as VARCHAR; nullable                 |
| `error_code`              | `VARCHAR`   | Nullable                                            |
| `error_message`           | `VARCHAR`   | Nullable                                            |
| `read_only`               | `BOOLEAN`   | Nullable                                            |
| `event_type`              | `VARCHAR`   | Nullable                                            |
| `recipient_account_id`    | `VARCHAR`   | Nullable                                            |
| `raw_event`               | `VARCHAR`   | Full original event JSON as VARCHAR; for ad-hoc queries |
| `geo_country_code`        | `VARCHAR`   | NULL unless GeoIP enrichment was performed          |
| `geo_country_name`        | `VARCHAR`   | NULL unless GeoIP enrichment was performed          |
| `geo_city`                | `VARCHAR`   | NULL unless GeoLite2-City database was used         |
| `geo_latitude`            | `DOUBLE`    | NULL unless GeoLite2-City database was used         |
| `geo_longitude`           | `DOUBLE`    | NULL unless GeoLite2-City database was used         |
| `geo_asn`                 | `VARCHAR`   | NULL unless GeoLite2-ASN database was used          |
| `geo_org`                 | `VARCHAR`   | NULL unless GeoLite2-ASN database was used          |

GeoIP columns are added via `ALTER TABLE … ADD COLUMN IF NOT EXISTS` (idempotent).  
Private/loopback IPs store a marker string (`"PRIVATE"`, `"LOOPBACK"`, `"LINK-LOCAL"`) instead of NULL.

**Design rationale**

- `userIdentity` nested fields are expanded into top-level columns so that common filters like `WHERE user_identity_type = 'Root'` are fast without `json_extract`.
- `request_parameters`, `response_elements`, and `raw_event` are stored as `VARCHAR` (not DuckDB JSON type) because their structure varies by API call. Use `json_extract_string(column, '$.field')` for ad-hoc queries.
- `raw_event` preserves the original event, ensuring that fields not yet in the schema remain accessible.

### `ingested_files`

Tracks which files have already been processed (ING-06 duplicate prevention).

| Column        | Type        | Notes                              |
|---------------|-------------|------------------------------------|
| `file_path`   | `VARCHAR`   | Primary key                        |
| `sha256`      | `VARCHAR`   | SHA-256 hex digest of file content |
| `ingested_at` | `TIMESTAMP` | Default: `current_timestamp`       |

A file is skipped on subsequent runs if its path **and** SHA-256 match a row in this table. If the file content changes (same name, different SHA-256), it will be re-ingested.

### Example queries

```sql
-- Count events per AWS service
SELECT event_source, COUNT(*) AS cnt
FROM cloudtrail_events
GROUP BY event_source
ORDER BY cnt DESC;

-- Find all root account activity
SELECT event_time, event_name, source_ip_address
FROM cloudtrail_events
WHERE user_identity_type = 'Root'
ORDER BY event_time;

-- Find API errors in the last 24 hours
SELECT event_time, event_name, error_code, error_message
FROM cloudtrail_events
WHERE error_code IS NOT NULL
  AND event_time >= now() - INTERVAL 1 DAY
ORDER BY event_time DESC;

-- Extract a field from request_parameters
SELECT event_name,
       json_extract_string(request_parameters, '$.bucketName') AS bucket
FROM cloudtrail_events
WHERE event_source = 's3.amazonaws.com';
```

---

## Module Structure

```
ingester/
├── Cargo.toml
├── README.md                    ← You are here
├── AGENTS.md                    ← Copilot agent instructions
├── src/
│   ├── main.rs                  # CLI entry point (clap) — ingest + enrich subcommands
│   ├── lib.rs                   # Public API re-exports
│   ├── parser.rs                # CloudTrail JSON parsing (serde)
│   ├── decompressor.rs          # Transparent gz decompression (flate2)
│   ├── db.rs                    # DuckDB schema + batch insert (Appender) + geo backfill
│   ├── ingest.rs                # Pipeline orchestration (rayon parallel → insert)
│   ├── enrich.rs                # Geo back-fill for existing rows (enrich subcommand)
│   ├── geoip.rs                 # MaxMind GeoLite2 lookup + private-IP classification
│   ├── date_filter.rs           # Date-range filter (--from / --to)
│   ├── path_filter.rs           # Glob path-pattern filter (--include / --exclude)
│   └── progress.rs              # Progress bar wrapper (indicatif)
└── tests/
    ├── cli_test.rs              # CLI integration tests (assert_cmd)
    ├── integration_test.rs      # End-to-end pipeline tests
    └── testdata/
        ├── single_event.json    # 1 CloudTrail event
        ├── multi_event.json     # 3 CloudTrail events
        ├── single_event.json.gz # 1 event, gzip-compressed
        └── malformed.json       # Invalid JSON (used to test error handling)
```

---

## Public API

The `ingester` crate exposes its internals as a library so that tests and future tooling can call the pipeline without spawning a subprocess.

```rust
use ingester::ingest::{ingest_with_filters, ingest_with_geoip, IngestStats};
use ingester::enrich::{enrich_existing, EnrichStats};
use ingester::geoip::{GeoipConfig, GeoipEnricher};
use ingester::date_filter::DateFilter;
use ingester::path_filter::PathFilter;
use ingester::db::{ensure_table, insert_events_with_geo};
use ingester::parser::{parse_cloudtrail_log, CloudTrailEvent, CloudTrailLog};
use ingester::decompressor::read_file_content;
```

### `ingest_with_filters`

```rust
pub fn ingest_with_filters(
    path: &Path,
    conn: &Connection,
    show_progress: bool,
    date_filter: &DateFilter,
    path_filter: &PathFilter,
) -> anyhow::Result<IngestStats>
```

Full-featured ingest without GeoIP. Applies date-range and glob path filters before any I/O.

### `ingest_with_geoip`

```rust
pub fn ingest_with_geoip(
    path: &Path,
    conn: &Connection,
    show_progress: bool,
    date_filter: &DateFilter,
    path_filter: &PathFilter,
    geoip: &GeoipEnricher,
) -> anyhow::Result<IngestStats>
```

Same as `ingest_with_filters` but enriches each event's `source_ip_address` with GeoIP data at ingest time.

### `enrich_existing`

```rust
pub fn enrich_existing(conn: &Connection, geoip: &GeoipEnricher) -> anyhow::Result<EnrichStats>
```

Back-fills geo columns for rows where `geo_country_code IS NULL`. Use this to add GeoIP data to a database ingested without the `--geoip-*` flags.

### `GeoipEnricher`

```rust
let enricher = GeoipEnricher::open(&GeoipConfig {
    city_db_path:    Some(PathBuf::from("/data/geoip/GeoLite2-City.mmdb")),
    country_db_path: None,
    asn_db_path:     Some(PathBuf::from("/data/geoip/GeoLite2-ASN.mmdb")),
})?;
```

### `DateFilter`

```rust
pub struct DateFilter { pub from: Option<NaiveDate>, pub to: Option<NaiveDate> }

impl DateFilter {
    pub fn from_strs(from: Option<&str>, to: Option<&str>) -> anyhow::Result<Self>;
    pub fn matches(&self, path: &Path) -> bool;
}
```

### `PathFilter`

```rust
impl PathFilter {
    pub fn from_strs(include: Option<&str>, exclude: Option<&str>) -> anyhow::Result<Self>;
    pub fn matches(&self, path: &Path) -> bool;
}
```

### `IngestStats` / `EnrichStats`

```rust
pub struct IngestStats {
    pub files_processed: usize,
    pub records_inserted: usize,
    pub errors: usize,
    pub elapsed_secs: f64,
}

pub struct EnrichStats {
    pub enriched_count: usize,
    pub skipped_count: usize,
    pub elapsed_secs: f64,
}
```

---

## Development

### Prerequisites

| Tool    | Version  | Install                        |
|---------|----------|--------------------------------|
| Rust    | stable   | `rustup update stable`         |
| Cargo   | (bundled)| —                              |

> **Note:** The `duckdb` crate uses the `bundled` feature, which compiles
> libduckdb from source. The **first build takes 5–10 minutes**. Subsequent
> builds are fast thanks to Cargo's incremental compilation.

### Build

```bash
cd ingester

# Debug build
cargo build

# Release build (recommended for large datasets)
cargo build --release
```

### Test

```bash
# Run all tests (unit + integration + CLI)
cargo test

# Run only unit tests (fast, no subprocess)
cargo test --lib

# Run a specific test by name
cargo test test_ingest_duplicate_prevention

# Run CLI integration tests
cargo test --test cli_test

# Run end-to-end pipeline tests
cargo test --test integration_test
```

All tests should pass:

```
running 65 tests   ← unit tests (parser, decompressor, db, ingest, date_filter, path_filter)
test result: ok. 65 passed

running 8 tests    ← CLI tests
test result: ok. 8 passed

running 2 tests    ← integration tests
test result: ok. 2 passed

running 1 test     ← doc-tests
test result: ok. 1 passed
```

### Lint & Format

```bash
# Check formatting (CI-safe, no changes written)
cargo fmt -- --check

# Apply formatting
cargo fmt

# Run Clippy with warnings treated as errors
cargo clippy -- -D warnings
```

---

## Architecture Notes

### Ingestion Pipeline

```
ingest_path / ingest_with_conn / ingest_with_filters
  │
  ├─ ensure_table()                Create schema if not exists (idempotent)
  ├─ fetch_ingested_files_map()    Single SELECT → HashMap<path, sha256>
  │
  └─ for each chunk of PARSE_CHUNK_SIZE files:
       │
       ├─ [PARALLEL – rayon]
       │    ├─ is_cloudtrail_file()   Skip non-.json / non-.json.gz files
       │    ├─ date_filter.matches()  Skip files outside --from / --to range
       │    ├─ path_filter.matches()  Skip files not matching --include / --exclude
       │    └─ parse_file_content()   Read bytes once → SHA-256 + decompress + parse
       │
       └─ [SERIAL – DuckDB writer]
            ├─ HashMap lookup          O(1) dedup check (no DB round-trip)
            ├─ insert_events()         Batch insert via duckdb::Appender
            └─ mark_ingested()         Record path + SHA-256 in ingested_files
```

### Performance

- **Parallel parsing**: `rayon` reads, decompresses, and parses up to
  `PARSE_CHUNK_SIZE` (default 64) files concurrently, using all CPU cores.
  Control the degree of parallelism with `--workers N` or the
  `RAYON_NUM_THREADS` environment variable.
- **Single file read**: each file is read exactly once — SHA-256 hashing,
  decompression, and JSON parsing share the same byte buffer.
- **Batch duplicate check**: the `ingested_files` table is loaded into a
  `HashMap` at start-up (one `SELECT`), replacing the previous pattern of one
  `SELECT` per file.
- **Chunked memory**: parsed events are held in memory only for the current
  chunk (≈ 64 files × average file size ≈ ≤ 64 MB), then dropped before the
  next chunk is fetched. Total memory does not scale with the total number of
  files.
- **Batch insert**: `duckdb::Appender` is used instead of individual `INSERT`
  statements, yielding 10–50× higher insert throughput.
- **Target throughput**: 10 GB in under 5 minutes on a standard laptop.

### DuckDB Access Model

| Component   | DuckDB mode  |
|-------------|--------------|
| ingester    | `READ_WRITE` |
| agent       | `READ_ONLY`  |
| dashboard   | `READ_ONLY`  |

Only one `ingester` process should be running at a time. Running the agent or
dashboard concurrently during ingestion is safe (DuckDB WAL handles reads), but
data written during the current run may not be visible until `flush` completes.

