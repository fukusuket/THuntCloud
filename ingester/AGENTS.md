# AGENTS.md — Ingester Module (Rust)

> This file provides GitHub Copilot with module-specific context for the `ingester` crate.
> For project-wide instructions, see [../.github/AGENTS.md](../.github/AGENTS.md).
> For feature requirements and priorities, see [../doc/PRD.md](../doc/PRD.md) — Section 6.1 (ingester Module).

## Module Purpose

The ingester reads AWS CloudTrail log files (JSON and `.json.gz`) from the local filesystem, parses them, and inserts the records into a DuckDB database. It is the **only** component that opens DuckDB in `READ_WRITE` mode. Optional GeoIP enrichment populates 7 geo columns using MaxMind GeoLite2 databases.

## Technology Stack

| Item              | Value                            |
| ----------------- | -------------------------------- |
| Language          | Rust (edition 2024)              |
| Build system      | Cargo                            |
| Key crates        | `serde`, `serde_json`, `flate2`, `duckdb`, `clap`, `anyhow`, `indicatif`, `walkdir`, `sha2`, `rayon`, `chrono`, `glob`, `maxminddb`, `tracing` |
| Test crates       | `tempfile`, `assert_cmd`, `predicates` |
| DuckDB mode       | `READ_WRITE`                     |

## Planned Module Structure

```
ingester/
├── Cargo.toml
├── src/
│   ├── main.rs            # CLI entry point (clap) — ingest + enrich subcommands
│   ├── lib.rs             # Public API re-exports
│   ├── parser.rs          # CloudTrail JSON parsing (serde)
│   ├── decompressor.rs    # Transparent gz decompression (flate2)
│   ├── db.rs              # DuckDB schema, batch insert (Appender), geo backfill
│   ├── ingest.rs          # Pipeline orchestration: walkdir → parallel parse → insert
│   ├── enrich.rs          # Geo back-fill for existing rows (enrich subcommand)
│   ├── geoip.rs           # MaxMind GeoLite2 lookup + private-IP classification
│   ├── date_filter.rs     # Date-range filter (--from / --to)
│   ├── path_filter.rs     # Glob path-pattern filter (--include / --exclude)
│   └── progress.rs        # Progress bar wrapper (indicatif)
├── tests/
│   ├── cli_test.rs          # CLI integration tests (assert_cmd)
│   ├── integration_test.rs  # End-to-end pipeline tests
│   └── testdata/
│       ├── single_event.json    # 1 CloudTrail event
│       ├── multi_event.json     # 3 CloudTrail events
│       ├── single_event.json.gz # 1 event, gzip-compressed
│       └── malformed.json       # Invalid JSON (error handling)
└── AGENTS.md              ← You are here
```

## Data Structures

```rust
/// A single CloudTrail event record.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CloudTrailEvent {
    #[serde(rename = "eventTime")]       pub event_time:      String,
    #[serde(rename = "eventName")]       pub event_name:      String,
    #[serde(rename = "eventSource")]     pub event_source:    String,
    #[serde(rename = "awsRegion")]       pub aws_region:      String,
    #[serde(rename = "sourceIPAddress")] pub source_ip_address: Option<String>,
    #[serde(rename = "userAgent")]       pub user_agent:      Option<String>,
    #[serde(rename = "userIdentity")]    pub user_identity:   Option<serde_json::Value>,
    #[serde(rename = "requestParameters")] pub request_parameters: Option<serde_json::Value>,
    #[serde(rename = "responseElements")] pub response_elements: Option<serde_json::Value>,
    #[serde(rename = "errorCode")]       pub error_code:      Option<String>,
    #[serde(rename = "errorMessage")]    pub error_message:   Option<String>,
    #[serde(rename = "readOnly")]        pub read_only:       Option<bool>,
    #[serde(rename = "eventType")]       pub event_type:      Option<String>,
    #[serde(rename = "recipientAccountId")] pub recipient_account_id: Option<String>,
}

/// Wrapper for the CloudTrail JSON file format `{"Records": [...]}`.
#[derive(Debug, Deserialize)]
pub struct CloudTrailLog {
    #[serde(rename = "Records")]
    pub records: Vec<CloudTrailEvent>,
}

/// Statistics returned after an ingestion run.
#[derive(Debug, Default)]
pub struct IngestStats {
    pub files_processed: usize,
    pub records_inserted: usize,
    pub errors: usize,
    pub elapsed_secs: f64,
}

/// Statistics returned after a geo-enrichment run.
#[derive(Debug, Default)]
pub struct EnrichStats {
    pub enriched_count: usize,
    pub skipped_count: usize,
    pub elapsed_secs: f64,
}

/// GeoIP lookup result for a single IP address.
pub struct GeoInfo {
    pub country_code: Option<String>,
    pub country_name: Option<String>,
    pub city:         Option<String>,
    pub latitude:     Option<f64>,
    pub longitude:    Option<f64>,
    pub asn:          Option<String>,
    pub org:          Option<String>,
}
```

## TDD Test Coverage (implemented)

Tests are organised by module. Add new tests in `#[cfg(test)] mod tests` within the same source file.

### parser.rs
- `test_parse_single_cloudtrail_event` — parse a minimal CloudTrail JSON record
- `test_parse_cloudtrail_records_array` — parse `{"Records": [...]}` with multiple events
- `test_parse_handles_missing_optional_fields` — missing optional fields do not panic
- `test_parse_malformed_json_returns_error` — invalid JSON returns `Err`
- `test_parse_empty_records_array` — `{"Records": []}` → empty vec, not error

### decompressor.rs
- `test_decompress_gz_file` — `.json.gz` decompresses correctly
- `test_detect_gz_by_extension` — `.json.gz` → decompress; `.json` → read directly
- `test_decompress_invalid_gz_returns_error` — corrupted gz returns `Err`

### db.rs
- `test_create_cloudtrail_table` — `ensure_table()` creates both tables
- `test_create_table_is_idempotent` — calling twice does not error
- `test_insert_single_event` — insert one event, verify query-back
- `test_insert_batch_events` — insert 100 events, verify row count
- `test_insert_event_with_null_fields` — `None` optional fields insert without error
- `test_ensure_geo_columns_adds_seven_columns` — 7 geo columns added via `ALTER TABLE`
- `test_ensure_geo_columns_is_idempotent` — calling twice does not error
- `test_insert_events_with_geo_populates_columns` — GeoInfo provided → correct DB values
- `test_insert_events_without_geo_columns_are_null` — no enricher → geo columns NULL
- `test_insert_events_private_ip_stores_marker` — `"PRIVATE"` marker stored for RFC-1918 IPs

### ingest.rs
- `test_ingest_single_json_file` — ingest `.json` → correct row count
- `test_ingest_single_gz_file` — ingest `.json.gz` → correct row count
- `test_ingest_directory` — ingest directory with multiple files → total row count
- `test_ingest_skips_non_json_files` — non-JSON files silently skipped
- `test_ingest_duplicate_prevention` — ingesting same file twice does not duplicate records
- `test_ingest_returns_stats` — returns `IngestStats { files_processed, records_inserted, errors, elapsed_secs }`

### geoip.rs
- `test_classify_rfc1918_*` — RFC-1918 addresses → `"PRIVATE"` marker
- `test_classify_loopback_*` — loopback addresses → `"LOOPBACK"` marker
- `test_classify_link_local_*` — link-local addresses → `"LINK-LOCAL"` marker
- `test_classify_public_returns_none` — public IPs → `None` (requires mmdb lookup)
- `test_parse_invalid_ip_string` — non-IP string → `Err`
- `test_enricher_private_ip_skips_mmdb_access` — private IPs bypass mmdb lookup
- `test_enricher_none_returns_all_none` — no enricher → all geo fields `None`

### enrich.rs
- `test_enrich_public_ip_writes_geo_data` — public IP rows get geo data via UPDATE
- `test_enrich_private_ip_writes_marker` — RFC-1918 IP rows get `"PRIVATE"` marker
- `test_enrich_skips_null_source_ip` — NULL source_ip rows are skipped
- `test_enrich_is_idempotent` — already-enriched rows (`geo_country_code IS NOT NULL`) are not overwritten
- `test_enrich_returns_stats` — returns `EnrichStats { enriched_count, skipped_count, elapsed_secs }`

### date_filter.rs / path_filter.rs
- `test_date_filter_*` — various from/to boundary cases; no-date files always match
- `test_path_filter_*` — include/exclude glob matching; `*` crosses path separators

### CLI (tests/cli_test.rs)
- `test_cli_ingest_command` — `ingester ingest --path <dir>` exits 0
- `test_cli_missing_path_shows_error` — missing `--path` produces usage error
- `test_cli_enrich_requires_geoip_arg` — `enrich` without GeoIP arg exits non-zero

## Testing Patterns

### Temporary DuckDB for Tests

```rust
#[cfg(test)]
mod tests {
    use tempfile::NamedTempFile;
    use duckdb::Connection;

    fn temp_db() -> (Connection, NamedTempFile) {
        let tmp = NamedTempFile::new().unwrap();
        let conn = Connection::open(tmp.path()).unwrap();
        (conn, tmp)
    }
}
```

## Error Handling

- Use `anyhow::Result` as the return type for all functions.
- Use `.with_context(|| format!("Failed to parse {}", path))` for context.
- Log errors via `tracing`; always propagate up to the CLI entry point.
- In `main.rs`, catch at top level and print with `eprintln!("error: {e:#}")`.

## Performance

- **Parallel parsing**: `rayon` reads, decompresses, and parses files concurrently (up to `PARSE_CHUNK_SIZE = 64` files per chunk). Control with `--workers N` or `RAYON_NUM_THREADS`.
- **Single file read**: each file is read once — SHA-256, decompression, and parsing share the same byte buffer.
- **Batch duplicate check**: `ingested_files` table loaded into a `HashMap` at startup (one `SELECT`).
- **Chunked memory**: events held in memory only for the current chunk, then dropped.
- **Batch insert**: `duckdb::Appender` yields 10–50× higher throughput vs. individual INSERTs.
- **Target**: 10 GB in under 5 minutes on a standard laptop.

## Language Policy

- **All Rust doc comments (`///`, `//!`), inline comments, and documentation MUST be written in English.**
