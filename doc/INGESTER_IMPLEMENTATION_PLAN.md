# Ingester Module — Implementation Plan

> Based on PRD.md Section 6.1 and ingester/AGENTS.md.
> All code comments, documentation, and commit messages MUST be written in English.
> This document is the source of truth for the ingester module implementation schedule.

---

## Overview

The ingester reads AWS CloudTrail log files (JSON and `.json.gz`) from the local filesystem, parses them, and inserts the records into a DuckDB database (READ_WRITE mode). It is implemented in Rust using strict TDD (Red-Green-Refactor).

**21 tests** are implemented across **5 phases** in order: `parser.rs` → `decompressor.rs` → `db.rs` → `ingest.rs` → `main.rs`.

---

## Phase 0 — Environment Setup (Estimated: 0.5h)

**Goal**: Create a minimal skeleton that builds successfully.

### Tasks

1. Add dependency crates to `Cargo.toml` (see list below)
2. Create `src/lib.rs` as an empty file so the `lib` crate can be referenced from `main.rs`
3. Create `tests/testdata/` directory and place 4 test data files
4. Verify `cargo build` passes (no tests written yet)

### Deliverables

- Updated `Cargo.toml`
- `src/lib.rs` (empty)
- `tests/testdata/single_event.json`
- `tests/testdata/multi_event.json`
- `tests/testdata/single_event.json.gz`
- `tests/testdata/malformed.json`

---

## Cargo.toml Dependencies

```toml
[dependencies]
serde              = { version = "1.0", features = ["derive"] }
serde_json         = "1.0"
flate2             = "1.0"
duckdb             = { version = "1.1", features = ["bundled"] }
clap               = { version = "4.5", features = ["derive"] }
anyhow             = "1.0"
indicatif          = "0.17"
walkdir            = "2.5"
sha2               = "0.10"
hex                = "0.4"
tracing            = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

[dev-dependencies]
tempfile           = "3.14"
assert_cmd         = "2.0"
predicates         = "3.1"
```

> **Note**: The `"bundled"` feature for `duckdb` statically links libduckdb, so no additional libraries are needed inside the Docker image. However, the initial build takes 5–10 minutes. Use Docker layer caching or `sccache` to avoid rebuilding dependencies on every change.

---

## Phase 1 — `parser.rs` (Estimated: 2h)

**Goal**: Make tests #1–#5 Green.

### TDD Cycle

| # | Test Name | Red: What fails | Green: Minimum implementation | Refactor |
|---|---|---|---|---|
| 1 | `test_parse_single_cloudtrail_event` | Compile error: `CloudTrailEvent` undefined | Define struct + `serde_json::from_str` with `CloudTrailLog` wrapper | Organize `#[serde(rename)]` attributes |
| 2 | `test_parse_cloudtrail_records_array` | `records.len()` assertion fails | Verified by test data (passes as-is) | — |
| 3 | `test_parse_handles_missing_optional_fields` | Deserialization panic for missing fields | Change all optional fields to `Option<T>` | Clean up field ordering |
| 4 | `test_parse_malformed_json_returns_error` | `unwrap()` panics | Change function to return `anyhow::Result` | Add `.with_context()` for better error messages |
| 5 | `test_parse_empty_records_array` | `records.len() == 0` assertion fails | Verify `{"Records": []}` returns empty vec | — |

### Public API

```rust
pub fn parse_cloudtrail_log(json: &str) -> anyhow::Result<CloudTrailLog>
```

### Deliverables

- `src/parser.rs` — `CloudTrailEvent`, `CloudTrailLog`, `parse_cloudtrail_log()`

---

## Phase 2 — `decompressor.rs` (Estimated: 1.5h)

**Goal**: Make tests #6–#8 Green.

### TDD Cycle

| # | Test Name | Red | Green | Refactor |
|---|---|---|---|---|
| 6 | `test_decompress_gz_file` | Compile error: function undefined | `GzDecoder` + `BufReader` → read to `String` | Extract `read_to_string` helper |
| 7 | `test_detect_gz_by_extension` | No branching for `.json` vs `.json.gz` | Use `Path::extension()` to check `"gz"` → branch | Merge into single public `read_file_content(path)` |
| 8 | `test_decompress_invalid_gz_returns_error` | `unwrap()` panics on corrupted data | Convert with `?` operator to `anyhow::Error` | Add `.with_context()` including `path` in message |

### Public API

```rust
pub fn read_file_content(path: &std::path::Path) -> anyhow::Result<String>
```

### Deliverables

- `src/decompressor.rs`

---

## Phase 3 — `db.rs` (Estimated: 3h)

**Goal**: Make tests #9–#13 Green. This is the most complex phase.

### DuckDB Table Schema Design

```sql
-- Main events table
CREATE TABLE IF NOT EXISTS cloudtrail_events (
    event_time               TIMESTAMP,
    event_name               VARCHAR,
    event_source             VARCHAR,
    aws_region               VARCHAR,
    source_ip_address        VARCHAR,
    user_agent               VARCHAR,
    user_identity_type       VARCHAR,     -- expanded from userIdentity.type
    user_identity_arn        VARCHAR,     -- expanded from userIdentity.arn
    user_identity_account_id VARCHAR,     -- expanded from userIdentity.accountId
    request_parameters       JSON,        -- stored as-is
    response_elements        JSON,        -- stored as-is
    error_code               VARCHAR,
    error_message            VARCHAR,
    read_only                BOOLEAN,
    event_type               VARCHAR,
    recipient_account_id     VARCHAR,
    raw_event                JSON         -- full original event JSON
);

-- Duplicate prevention table (ING-06)
CREATE TABLE IF NOT EXISTS ingested_files (
    file_path   VARCHAR PRIMARY KEY,
    sha256      VARCHAR NOT NULL,
    ingested_at TIMESTAMP DEFAULT current_timestamp
);
```

**Schema design rationale**:
- `userIdentity` fields are expanded (type/arn/accountId) to enable fast queries like `WHERE user_identity_type = 'Root'`
- `request_parameters` / `response_elements` are kept as JSON since their structure varies widely. DuckDB's `json_extract_string()` enables ad-hoc analysis
- `raw_event` stores the original JSON, allowing access to future fields not covered by the schema
- Using `TIMESTAMP` type enables time-range queries with `BETWEEN` and `date_trunc()`

### TDD Cycle

| # | Test Name | Minimum Green Implementation |
|---|---|---|
| 9  | `test_create_cloudtrail_table`       | `ensure_table(conn)` → execute `CREATE TABLE IF NOT EXISTS` SQL |
| 10 | `test_create_table_is_idempotent`    | Verify calling `ensure_table()` twice does not error (`IF NOT EXISTS`) |
| 11 | `test_insert_single_event`           | `INSERT INTO` + verify with `SELECT COUNT(*)` |
| 12 | `test_insert_batch_events`           | Batch insert 100 events using `duckdb::Appender` |
| 13 | `test_insert_event_with_null_fields` | Verify `Option::None` → `NULL` mapping works without error |

### Public API

```rust
pub fn ensure_table(conn: &duckdb::Connection) -> anyhow::Result<()>
pub fn insert_events(conn: &duckdb::Connection, events: &[CloudTrailEvent]) -> anyhow::Result<usize>
```

**Batch insert strategy**: Use `duckdb::Appender` obtained via `conn.appender("cloudtrail_events")`. Bind fields one by one with `appender.append_row(...)`. Commit with `appender.flush()`. Target batch size: 1,000 records per flush.

### Deliverables

- `src/db.rs`

---

## Phase 4 — `ingest.rs` + `progress.rs` (Estimated: 3h)

**Goal**: Make tests #14–#19 Green.

### Duplicate Prevention Strategy (ING-06)

**Method: SHA-256 checksum + `ingested_files` table**

```
Ingestion flow:
  1. Compute SHA-256 of file content
  2. Query: SELECT sha256 FROM ingested_files WHERE file_path = ?
  3. Match found → skip (log only, do not increment stats.errors)
  4. No match → proceed with ingestion
  5. On success → INSERT INTO ingested_files (path, sha256, now())
```

**Design decisions**:
- SHA-256 rather than filename alone: detects overwritten files with the same name
- SHA-256 also detects re-downloaded files (same content, different download path) as duplicates
- `ingested_files` table lives inside DuckDB — no separate file management required

### TDD Cycle

| # | Test Name | What to Verify |
|---|---|---|
| 14 | `test_ingest_single_json_file`      | `IngestStats.records_inserted == 1`, `files_processed == 1` |
| 15 | `test_ingest_single_gz_file`        | Same result via gz decompression |
| 16 | `test_ingest_directory`             | `walkdir` scans multiple files; total row count matches |
| 17 | `test_ingest_skips_non_json_files`  | `.txt` / `.log` files are not added to `records_inserted` |
| 18 | `test_ingest_duplicate_prevention`  | Ingesting the same file twice does not double the row count |
| 19 | `test_ingest_returns_stats`         | `elapsed_secs > 0.0`, `errors == 0` |

### Public API

```rust
pub fn ingest_path(path: &std::path::Path, db_path: &std::path::Path) -> anyhow::Result<IngestStats>
```

### `progress.rs` Design

- Use `indicatif::ProgressBar` to display file count spinner and record count
- `ProgressBar::new_spinner()` → during directory scan
- `ProgressBar::new(total_files)` → per-file progress bar
- In test environments, suppress output with `indicatif::ProgressDrawTarget::hidden()`
- Expose progress updates as an optional callback (`Option<Box<dyn Fn(usize)>>`) for testability

### Deliverables

- `src/ingest.rs`
- `src/progress.rs`

---

## Phase 5 — `main.rs` + CLI + Integration Tests (Estimated: 2h)

**Goal**: Make tests #20–#21 Green and pass the integration tests.

### CLI Interface Design (clap derive macro)

```
USAGE:
    ingester <SUBCOMMAND>

SUBCOMMANDS:
    ingest    Ingest CloudTrail log files into DuckDB

OPTIONS (ingest subcommand):
    -p, --path <PATH>        Path to a file or directory containing CloudTrail logs [required]
    -d, --db   <DB_PATH>     Path to DuckDB database file [default: /data/threat_hunting.db]
        --no-progress        Disable progress bar output
    -h, --help               Print help information
    -V, --version            Print version information
```

**Example usage**:
```bash
ingester ingest --path /logs/cloudtrail/ --db /data/threat_hunting.db
```

### TDD Cycle

| # | Test Name | Tool | What to Verify |
|---|---|---|---|
| 20 | `test_cli_ingest_command`          | `assert_cmd::Command` | Exit code 0, output includes `records_inserted` |
| 21 | `test_cli_missing_path_shows_error` | `assert_cmd::Command` | Non-zero exit code, stderr includes `error:` |

### Integration Tests (`tests/integration_test.rs`)

- Use `tempfile::TempDir` + `tempfile::NamedTempFile` to create a temporary filesystem and DuckDB
- Pass all files in `tests/testdata/` through the full pipeline
- Verify the final record count matches expectations

### Deliverables

- Updated `src/main.rs`
- Updated `src/lib.rs` (public re-exports)
- `tests/integration_test.rs`

---

## Performance Optimization Techniques

| Technique | Location | Effect |
|---|---|---|
| `BufReader::with_capacity(8MB)` | `decompressor.rs` | Reduces number of system calls |
| `duckdb::Appender` (batch size: 1,000) | `db.rs` | ~10–50x faster than individual INSERTs |
| Reuse `String` buffer (`String::clear()`) | `ingest.rs` | Reduces JSON buffer allocations |
| Sequential file processing (v1.0) | `ingest.rs` | Simple and sufficient for v1.0; parallel processing can be added in v2.0 |
| `flate2::bufread::GzDecoder` | `decompressor.rs` | Efficient BufRead support for gz streams |

---

## Risks and Notes

1. **`duckdb` crate build time**: The `"bundled"` feature causes the first build to take 5–10 minutes. Use `sccache` or Docker layer caching to separate dependency builds.
2. **`event_time` type conversion**: CloudTrail returns timestamps as strings like `"2024-01-15T10:30:00Z"`. DuckDB's `Appender` auto-casts string bindings to `TIMESTAMP`. On conversion failure, record the error and continue.
3. **`userIdentity` JSON expansion**: `user_identity.get("type")` may be `None` for non-IAM events. Always handle as `Option`.
4. **DuckDB WAL and concurrent connections**: When the ingester holds a `READ_WRITE` lock, agent/dashboard connecting `READ_ONLY` may not see uncommitted WAL data. Recommend Docker Compose profiles to prevent simultaneous startup of `ingester` and `agent` (document in `doc/DEVELOPMENT.md`).
5. **Rust edition 2024**: The project uses `edition = "2024"`. No async code is used in v1.0, so impact is minimal. Leverage `let-else` and other new syntax where appropriate.
6. **SHA-256 computation cost**: For large files (hundreds of MB), SHA-256 alone can take several seconds. Consider computing the hash incrementally while reading (`std::io::Read` + rolling hash), or use filename + file size + mtime as a fast-path check.

---

## Module Dependency Graph

```
main.rs
  └── ingest.rs
        ├── parser.rs
        ├── decompressor.rs
        ├── db.rs
        └── progress.rs
lib.rs  (re-exports all public APIs)
```

---

## File List (Final State)

```
ingester/
├── Cargo.toml                         # Updated with all dependencies
├── src/
│   ├── main.rs                        # CLI entry point (clap)
│   ├── lib.rs                         # Public API re-exports
│   ├── parser.rs                      # CloudTrail JSON parsing
│   ├── decompressor.rs                # gz decompression (flate2)
│   ├── db.rs                          # DuckDB connection, table creation, batch insert
│   ├── ingest.rs                      # Orchestration: walk → parse → insert
│   └── progress.rs                    # Progress bar (indicatif)
├── tests/
│   ├── integration_test.rs            # End-to-end ingestion tests
│   └── testdata/
│       ├── single_event.json
│       ├── multi_event.json
│       ├── single_event.json.gz
│       └── malformed.json
└── AGENTS.md
```

---

## Commit Convention

Follow Conventional Commits format:

```
feat(ingester): add CloudTrail JSON parser
test(ingester): add parser unit tests (Red phase)
feat(ingester): implement parser to pass unit tests (Green phase)
refactor(ingester): extract parse_cloudtrail_log helper
```

---

*This document is the implementation plan for the ingester module. Update it as implementation progresses.*

