# AGENTS.md — Ingester Module (Rust)

> This file provides GitHub Copilot with module-specific context for the `ingester` crate.
> For project-wide instructions, see [../.github/AGENTS.md](../.github/AGENTS.md).
> For feature requirements and priorities, see [../doc/PRD.md](../doc/PRD.md) — Section 6.1 (ingester Module).

## Module Purpose

The ingester reads AWS CloudTrail log files (JSON and `.json.gz`) from the local filesystem, parses them, and inserts the records into a DuckDB database. It is the **only** component that opens DuckDB in `READ_WRITE` mode.

## Technology Stack

| Item              | Value                            |
| ----------------- | -------------------------------- |
| Language          | Rust (edition 2024)              |
| Build system      | Cargo                            |
| Key crates        | `serde`, `serde_json`, `flate2`, `duckdb`, `clap`, `anyhow`, `indicatif`, `walkdir`, `sha2` |
| Test crates       | `tempfile`, `assert_cmd` (optional for CLI integration tests) |
| DuckDB mode       | `READ_WRITE`                     |

## Planned Module Structure

```
ingester/
├── Cargo.toml
├── src/
│   ├── main.rs            # CLI entry point (clap)
│   ├── lib.rs             # Public API re-exports
│   ├── parser.rs          # CloudTrail JSON parsing
│   ├── decompressor.rs    # gz decompression (flate2)
│   ├── db.rs              # DuckDB connection, table creation, batch insert
│   ├── ingest.rs          # Orchestration: walk directory → parse → insert
│   └── progress.rs        # Progress bar (indicatif)
├── tests/
│   ├── integration_test.rs  # End-to-end ingestion tests
│   └── testdata/
│       ├── single_event.json
│       ├── multi_event.json
│       ├── single_event.json.gz
│       └── malformed.json
└── AGENTS.md              ← You are here
```

## TDD Test List

When implementing the ingester, follow this ordered test list. Each item should be a `#[test]` function. Proceed one test at a time using Red-Green-Refactor.

### parser.rs

1. `test_parse_single_cloudtrail_event` — Parse a minimal CloudTrail JSON record into a struct.
2. `test_parse_cloudtrail_records_array` — Parse a CloudTrail file containing `{"Records": [...]}` with multiple events.
3. `test_parse_handles_missing_optional_fields` — Fields like `errorCode` may be absent; parse should not panic.
4. `test_parse_malformed_json_returns_error` — Invalid JSON input returns an appropriate error.
5. `test_parse_empty_records_array` — `{"Records": []}` returns an empty vec, not an error.

### decompressor.rs

6. `test_decompress_gz_file` — Read a `.json.gz` file and produce the decompressed JSON string.
7. `test_detect_gz_by_extension` — `.json.gz` → decompress; `.json` → read directly.
8. `test_decompress_invalid_gz_returns_error` — Corrupted gz file returns an error.

### db.rs

9. `test_create_cloudtrail_table` — `ensure_table()` creates the `cloudtrail_events` table in a temp DuckDB.
10. `test_create_table_is_idempotent` — Calling `ensure_table()` twice does not error.
11. `test_insert_single_event` — Insert one parsed event and verify it can be queried back.
12. `test_insert_batch_events` — Insert 100 events in a batch and verify the row count.
13. `test_insert_event_with_null_fields` — Events with `None` optional fields are inserted without error.

### ingest.rs

14. `test_ingest_single_json_file` — Ingest one `.json` file into a temp DuckDB; verify row count.
15. `test_ingest_single_gz_file` — Ingest one `.json.gz` file; verify row count.
16. `test_ingest_directory` — Ingest a directory with multiple files; verify total row count.
17. `test_ingest_skips_non_json_files` — Non-JSON files in the directory are silently skipped.
18. `test_ingest_duplicate_prevention` — Ingesting the same file twice does not duplicate records (if ING-06 is implemented).
19. `test_ingest_returns_stats` — The ingest function returns `IngestStats { files_processed, records_inserted, errors }`.

### main.rs (CLI integration)

20. `test_cli_ingest_command` — Running `ingester ingest --path <dir>` exits successfully.
21. `test_cli_missing_path_shows_error` — Running without `--path` produces a usage error.

## Data Structures

```rust
use serde::{Deserialize, Serialize};

/// A single CloudTrail event record.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CloudTrailEvent {
    #[serde(rename = "eventTime")]
    pub event_time: String,
    #[serde(rename = "eventName")]
    pub event_name: String,
    #[serde(rename = "eventSource")]
    pub event_source: String,
    #[serde(rename = "awsRegion")]
    pub aws_region: String,
    #[serde(rename = "sourceIPAddress")]
    pub source_ip_address: Option<String>,
    #[serde(rename = "userAgent")]
    pub user_agent: Option<String>,
    #[serde(rename = "userIdentity")]
    pub user_identity: Option<serde_json::Value>,
    #[serde(rename = "requestParameters")]
    pub request_parameters: Option<serde_json::Value>,
    #[serde(rename = "responseElements")]
    pub response_elements: Option<serde_json::Value>,
    #[serde(rename = "errorCode")]
    pub error_code: Option<String>,
    #[serde(rename = "errorMessage")]
    pub error_message: Option<String>,
    #[serde(rename = "readOnly")]
    pub read_only: Option<bool>,
    #[serde(rename = "eventType")]
    pub event_type: Option<String>,
    #[serde(rename = "recipientAccountId")]
    pub recipient_account_id: Option<String>,
}

/// Wrapper for the CloudTrail JSON file format.
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
```

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

    #[test]
    fn test_example() {
        let (conn, _tmp) = temp_db();
        // Use conn for testing...
    }
}
```

### Test Data

Place minimal CloudTrail JSON files in `tests/testdata/`. Example:

```json
{
  "Records": [
    {
      "eventTime": "2024-01-15T10:30:00Z",
      "eventName": "DescribeInstances",
      "eventSource": "ec2.amazonaws.com",
      "awsRegion": "us-east-1",
      "sourceIPAddress": "198.51.100.1",
      "userAgent": "aws-cli/2.0",
      "userIdentity": {
        "type": "IAMUser",
        "arn": "arn:aws:iam::123456789012:user/testuser",
        "accountId": "123456789012"
      },
      "readOnly": true,
      "eventType": "AwsApiCall",
      "recipientAccountId": "123456789012"
    }
  ]
}
```

### Creating Test gz Files

```rust
use flate2::write::GzEncoder;
use flate2::Compression;
use std::io::Write;

fn create_test_gz(json_content: &str, path: &std::path::Path) {
    let file = std::fs::File::create(path).unwrap();
    let mut encoder = GzEncoder::new(file, Compression::default());
    encoder.write_all(json_content.as_bytes()).unwrap();
    encoder.finish().unwrap();
}
```

## Error Handling

- Use `anyhow::Result` as the return type for all functions.
- Use `anyhow::Context` for adding context to errors (e.g., `.with_context(|| format!("Failed to parse {}", path))`).
- Log errors with `tracing` or `log` crate, but always propagate them up.
- In the CLI, catch errors at the top level and print a user-friendly message.

## Performance Considerations

- Use **batch inserts** (prepared statement + appender) rather than individual INSERT statements.
- Use `BufReader` for file I/O.
- Process files sequentially in v1.0 (parallel file processing can be added later).
- Target: 10 GB ingestion in under 5 minutes; 50 GB on 16 GB RAM.

