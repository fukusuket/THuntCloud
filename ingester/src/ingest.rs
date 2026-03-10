//! Ingestion orchestration: walk a path → decompress → parse → insert into DuckDB.
//!
//! This is the top-level entry point for the ingestion pipeline.
//! It ties together [`crate::decompressor`], [`crate::parser`], and [`crate::db`].

use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result};
use duckdb::Connection;
use rayon::prelude::*;
use sha2::{Digest, Sha256};
use walkdir::WalkDir;

use crate::db::{ensure_table, insert_events};
use crate::decompressor::read_file_content;
use crate::parser::{CloudTrailEvent, parse_cloudtrail_log};
use crate::progress::ProgressReporter;

/// Statistics returned after a completed ingestion run.
#[derive(Debug, Default)]
pub struct IngestStats {
    /// Number of files successfully processed.
    pub files_processed: usize,
    /// Total number of event records inserted into DuckDB.
    pub records_inserted: usize,
    /// Number of files that produced an error (skipped, not inserted).
    pub errors: usize,
    /// Wall-clock time for the entire run in seconds.
    pub elapsed_secs: f64,
}

/// Ingest all CloudTrail log files found at `path` into the DuckDB database
/// at `db_path`.
///
/// `path` may be a single file or a directory. Directories are walked
/// recursively. Files whose extension is neither `.json` nor `.json.gz` are
/// silently skipped. Ingesting the same file a second time is a no-op (files
/// are identified by their SHA-256 checksum stored in `ingested_files`).
///
/// Returns [`IngestStats`] describing what happened.
pub fn ingest_path(path: &Path, db_path: &Path) -> Result<IngestStats> {
    let conn = Connection::open(db_path)
        .with_context(|| format!("Failed to open DuckDB at {}", db_path.display()))?;
    ingest_with_conn(path, &conn)
}

/// Internal implementation that accepts an existing [`Connection`].
///
/// Separated from [`ingest_path`] so that tests can pass an in-memory
/// connection without touching the filesystem for the database file.
/// The progress bar is always hidden; use [`ingest_with_progress`] when
/// a visible bar is desired.
pub fn ingest_with_conn(path: &Path, conn: &Connection) -> Result<IngestStats> {
    ingest_with_progress(path, conn, false)
}

/// A file that has passed the duplicate-check and is ready to be parsed.
struct FileToProcess {
    path: PathBuf,
    sha256: String,
}

/// The parsed result of a single CloudTrail log file.
struct ParsedFile {
    path: PathBuf,
    sha256: String,
    records: Vec<CloudTrailEvent>,
}

/// Read a file, compute its SHA-256 digest, and parse the CloudTrail records.
///
/// Returns `(sha256_hex, records)`. This function is CPU/IO-bound and is
/// designed to be called from a `rayon` parallel iterator.
pub fn parse_file_content(path: &Path) -> Result<(String, Vec<CloudTrailEvent>)> {
    let bytes =
        std::fs::read(path).with_context(|| format!("Failed to read {}", path.display()))?;
    let sha256 = hex::encode(Sha256::digest(&bytes));

    let content = if path.extension().and_then(|e| e.to_str()) == Some("gz") {
        use flate2::bufread::GzDecoder;
        use std::io::{BufReader, Read};
        let mut decoder = GzDecoder::new(BufReader::new(bytes.as_slice()));
        let mut s = String::new();
        decoder
            .read_to_string(&mut s)
            .with_context(|| format!("Failed to decompress {}", path.display()))?;
        s
    } else {
        String::from_utf8(bytes)
            .with_context(|| format!("File is not valid UTF-8: {}", path.display()))?
    };

    let log = parse_cloudtrail_log(&content)
        .with_context(|| format!("Failed to parse {}", path.display()))?;
    Ok((sha256, log.records))
}

/// Same as [`ingest_with_conn`] but controls whether the progress bar is
/// displayed on the terminal.
///
/// Processing is split into three phases:
/// 1. **Serial** — SHA-256 + duplicate check per file.
/// 2. **Parallel** — file read, gz decompress, JSON parse (via `rayon`).
/// 3. **Serial** — DuckDB INSERT + mark-ingested + stats update.
pub fn ingest_with_progress(
    path: &Path,
    conn: &Connection,
    show_progress: bool,
) -> Result<IngestStats> {
    ensure_table(conn)?;

    let start = Instant::now();
    let mut stats = IngestStats::default();

    // Collect candidate files.
    let files: Vec<_> = WalkDir::new(path)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
        .filter(|e| is_cloudtrail_file(e.path()))
        .collect();

    let reporter = if show_progress {
        ProgressReporter::new(files.len() as u64)
    } else {
        ProgressReporter::hidden()
    };

    // ── Phase 1: serial duplicate check (sha256 only — fast path) ─────────
    // We only compute the sha256 here to decide which files to parse.
    // The actual read+parse happens in parallel in Phase 2.
    let mut to_process: Vec<FileToProcess> = Vec::new();
    for entry in &files {
        let file_path = entry.path();
        match sha256_of_file(file_path) {
            Err(e) => {
                stats.errors += 1;
                eprintln!("Error hashing {}: {e:#}", file_path.display());
                reporter.inc(stats.records_inserted);
            }
            Ok(sha256) => {
                if is_already_ingested(file_path, &sha256, conn) {
                    // Already in DB — count as processed, skip re-insert.
                    stats.files_processed += 1;
                    reporter.inc(stats.records_inserted);
                } else {
                    to_process.push(FileToProcess {
                        path: file_path.to_path_buf(),
                        sha256,
                    });
                }
            }
        }
    }

    // ── Phase 2: parallel decompress + parse (reuses bytes already on disk) -
    // Files are read a second time here, but now in parallel across all cores.
    // The sha256 from Phase 1 is kept to avoid a third read in Phase 3.
    let parse_results: Vec<Result<ParsedFile>> = to_process
        .into_par_iter()
        .map(|f| {
            let content = read_file_content(&f.path)?;
            let log = parse_cloudtrail_log(&content)
                .with_context(|| format!("Failed to parse {}", f.path.display()))?;
            Ok(ParsedFile {
                path: f.path,
                sha256: f.sha256,
                records: log.records,
            })
        })
        .collect();

    // ── Phase 3: serial INSERT + mark-ingested + stats ─────────────────────
    for result in parse_results {
        match result {
            Err(e) => {
                stats.errors += 1;
                eprintln!("Error processing file: {e:#}");
            }
            Ok(parsed) => {
                match insert_events(conn, &parsed.records)
                    .and_then(|n| mark_ingested(&parsed.path, &parsed.sha256, conn).map(|_| n))
                {
                    Err(e) => {
                        stats.errors += 1;
                        eprintln!("Error inserting {}: {e:#}", parsed.path.display());
                    }
                    Ok(n) => {
                        stats.files_processed += 1;
                        stats.records_inserted += n;
                    }
                }
            }
        }
        reporter.inc(stats.records_inserted);
    }

    reporter.finish();
    stats.elapsed_secs = start.elapsed().as_secs_f64();
    Ok(stats)
}

/// Returns `true` if `path` has an extension that indicates a CloudTrail log.
fn is_cloudtrail_file(path: &Path) -> bool {
    match path.extension().and_then(|e| e.to_str()) {
        Some("json") => true,
        Some("gz") => path
            .file_name()
            .and_then(|n| n.to_str())
            .map(|n| n.ends_with(".json.gz"))
            .unwrap_or(false),
        _ => false,
    }
}

/// Compute the SHA-256 hex digest of the file at `path`.
fn sha256_of_file(path: &Path) -> Result<String> {
    let bytes =
        std::fs::read(path).with_context(|| format!("Failed to read {}", path.display()))?;
    let digest = Sha256::digest(&bytes);
    Ok(hex::encode(digest))
}

/// Returns `true` if the file has already been ingested (checksum match).
fn is_already_ingested(path: &Path, sha256: &str, conn: &Connection) -> bool {
    let path_str = path.to_string_lossy();
    conn.query_row(
        "SELECT sha256 FROM ingested_files WHERE file_path = ?",
        [path_str.as_ref()],
        |row| row.get::<_, String>(0),
    )
    .map(|stored| stored == sha256)
    .unwrap_or(false)
}

/// Record that `path` with checksum `sha256` has been ingested.
fn mark_ingested(path: &Path, sha256: &str, conn: &Connection) -> Result<()> {
    let path_str = path.to_string_lossy();
    conn.execute(
        "INSERT OR REPLACE INTO ingested_files (file_path, sha256) VALUES (?, ?)",
        duckdb::params![path_str.as_ref(), sha256],
    )
    .with_context(|| format!("Failed to record ingested file {}", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use duckdb::Connection;
    use std::io::Write;
    use tempfile::{NamedTempFile, TempDir};

    /// Shared CloudTrail JSON content used across multiple tests.
    const SINGLE_EVENT_JSON: &str = r#"{
        "Records": [{
            "eventTime": "2024-01-15T10:30:00Z",
            "eventName": "DescribeInstances",
            "eventSource": "ec2.amazonaws.com",
            "awsRegion": "us-east-1",
            "sourceIPAddress": "198.51.100.1",
            "userAgent": "aws-cli/2.0",
            "readOnly": true,
            "eventType": "AwsApiCall",
            "recipientAccountId": "123456789012"
        }]
    }"#;

    const THREE_EVENT_JSON: &str = r#"{
        "Records": [
            {
                "eventTime": "2024-01-15T10:30:00Z",
                "eventName": "DescribeInstances",
                "eventSource": "ec2.amazonaws.com",
                "awsRegion": "us-east-1"
            },
            {
                "eventTime": "2024-01-15T11:00:00Z",
                "eventName": "CreateBucket",
                "eventSource": "s3.amazonaws.com",
                "awsRegion": "us-west-2"
            },
            {
                "eventTime": "2024-01-15T12:00:00Z",
                "eventName": "AssumeRole",
                "eventSource": "sts.amazonaws.com",
                "awsRegion": "us-east-1"
            }
        ]
    }"#;

    /// Write `content` to a temporary `.json` file and return the handle.
    fn write_json_file(content: &str) -> NamedTempFile {
        let mut tmp = tempfile::Builder::new().suffix(".json").tempfile().unwrap();
        tmp.write_all(content.as_bytes()).unwrap();
        tmp.flush().unwrap();
        tmp
    }

    /// Write `content` as a gzip-compressed `.json.gz` file and return the handle.
    fn write_gz_file(content: &str) -> NamedTempFile {
        use flate2::Compression;
        use flate2::write::GzEncoder;
        let tmp = tempfile::Builder::new()
            .suffix(".json.gz")
            .tempfile()
            .unwrap();
        let file = std::fs::File::create(tmp.path()).unwrap();
        let mut enc = GzEncoder::new(file, Compression::default());
        enc.write_all(content.as_bytes()).unwrap();
        enc.finish().unwrap();
        tmp
    }

    /// Open an in-memory DuckDB and ensure the schema exists.
    fn setup_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        ensure_table(&conn).unwrap();
        conn
    }

    // ── Helper: count rows in cloudtrail_events ───────────────────────────────
    fn row_count(conn: &Connection) -> i64 {
        conn.query_row("SELECT COUNT(*) FROM cloudtrail_events", [], |r| r.get(0))
            .unwrap()
    }

    // Test #14: Ingest one `.json` file into a temp DuckDB; verify row count.
    #[test]
    fn test_ingest_single_json_file() {
        let tmp = write_json_file(SINGLE_EVENT_JSON);
        let conn = setup_db();

        let stats = ingest_with_conn(tmp.path(), &conn).expect("ingest should succeed");

        assert_eq!(stats.files_processed, 1);
        assert_eq!(stats.records_inserted, 1);
        assert_eq!(stats.errors, 0);
        assert_eq!(row_count(&conn), 1);
    }

    // Test #15: Ingest one `.json.gz` file; verify row count.
    #[test]
    fn test_ingest_single_gz_file() {
        let tmp = write_gz_file(SINGLE_EVENT_JSON);
        let conn = setup_db();

        let stats = ingest_with_conn(tmp.path(), &conn).expect("ingest should succeed");

        assert_eq!(stats.files_processed, 1);
        assert_eq!(stats.records_inserted, 1);
        assert_eq!(stats.errors, 0);
        assert_eq!(row_count(&conn), 1);
    }

    // Test #16: Ingest a directory with multiple files; verify total row count.
    #[test]
    fn test_ingest_directory() {
        let dir = TempDir::new().unwrap();

        // Write two JSON files: 1 event + 3 events = 4 total.
        std::fs::write(dir.path().join("a.json"), SINGLE_EVENT_JSON).unwrap();
        std::fs::write(dir.path().join("b.json"), THREE_EVENT_JSON).unwrap();

        let conn = setup_db();
        let stats = ingest_with_conn(dir.path(), &conn).expect("ingest should succeed");

        assert_eq!(stats.files_processed, 2);
        assert_eq!(stats.records_inserted, 4);
        assert_eq!(stats.errors, 0);
        assert_eq!(row_count(&conn), 4);
    }

    // Test #17: Non-JSON files in the directory are silently skipped.
    #[test]
    fn test_ingest_skips_non_json_files() {
        let dir = TempDir::new().unwrap();

        std::fs::write(dir.path().join("log.txt"), "not a json file").unwrap();
        std::fs::write(dir.path().join("data.csv"), "col1,col2\n1,2").unwrap();
        std::fs::write(dir.path().join("event.json"), SINGLE_EVENT_JSON).unwrap();

        let conn = setup_db();
        let stats = ingest_with_conn(dir.path(), &conn).expect("ingest should succeed");

        // Only event.json should have been processed.
        assert_eq!(stats.files_processed, 1);
        assert_eq!(stats.records_inserted, 1);
        assert_eq!(stats.errors, 0);
    }

    // Test #18: Ingesting the same file twice does not duplicate records.
    #[test]
    fn test_ingest_duplicate_prevention() {
        let tmp = write_json_file(SINGLE_EVENT_JSON);
        let conn = setup_db();

        // First ingest — should insert 1 record.
        let stats1 = ingest_with_conn(tmp.path(), &conn).expect("first ingest should succeed");
        assert_eq!(stats1.records_inserted, 1);

        // Second ingest — file is already tracked in ingested_files; should be skipped.
        let stats2 = ingest_with_conn(tmp.path(), &conn).expect("second ingest should succeed");
        assert_eq!(stats2.records_inserted, 0);
        assert_eq!(
            stats2.files_processed, 1,
            "file should still count as processed"
        );

        // Row count must not have doubled.
        assert_eq!(row_count(&conn), 1);
    }

    // Test #19: The ingest function returns IngestStats with meaningful values.
    #[test]
    fn test_ingest_returns_stats() {
        let tmp = write_json_file(SINGLE_EVENT_JSON);
        let conn = setup_db();

        let stats = ingest_with_conn(tmp.path(), &conn).expect("ingest should succeed");

        assert_eq!(stats.files_processed, 1);
        assert_eq!(stats.records_inserted, 1);
        assert_eq!(stats.errors, 0);
        assert!(
            stats.elapsed_secs >= 0.0,
            "elapsed_secs should be non-negative"
        );
    }

    // Test #22: ingest_with_progress uses a visible reporter when show_progress=true.
    // The ProgressReporter::new() path is exercised (no panic, correct stats).
    #[test]
    fn test_ingest_with_progress_show_true() {
        let tmp = write_json_file(SINGLE_EVENT_JSON);
        let conn = setup_db();

        // show_progress=true should not panic and should return correct stats.
        let stats = ingest_with_progress(tmp.path(), &conn, true)
            .expect("ingest with visible progress should succeed");

        assert_eq!(stats.files_processed, 1);
        assert_eq!(stats.records_inserted, 1);
        assert_eq!(stats.errors, 0);
    }

    // Test #23: ingest_with_progress uses a hidden reporter when show_progress=false.
    #[test]
    fn test_ingest_with_progress_show_false() {
        let tmp = write_json_file(SINGLE_EVENT_JSON);
        let conn = setup_db();

        let stats = ingest_with_progress(tmp.path(), &conn, false)
            .expect("ingest with hidden progress should succeed");

        assert_eq!(stats.files_processed, 1);
        assert_eq!(stats.records_inserted, 1);
        assert_eq!(stats.errors, 0);
    }

    // Test #24: Parallel ingestion of 10 files produces correct aggregate stats.
    // This is the primary correctness guard for the parallel implementation.
    #[test]
    fn test_ingest_parallel_correctness_10_files() {
        let dir = TempDir::new().unwrap();

        // Write 10 single-event JSON files.
        for i in 0..10 {
            std::fs::write(
                dir.path().join(format!("event_{i:02}.json")),
                SINGLE_EVENT_JSON,
            )
            .unwrap();
        }

        let conn = setup_db();
        let stats = ingest_with_conn(dir.path(), &conn).expect("parallel ingest should succeed");

        assert_eq!(
            stats.files_processed, 10,
            "all 10 files should be processed"
        );
        assert_eq!(stats.records_inserted, 10, "10 records total (1 per file)");
        assert_eq!(stats.errors, 0, "no errors expected");
        assert_eq!(row_count(&conn), 10, "10 rows in DB");
    }

    // Test #25: parse_file_content correctly reads and parses a plain JSON file.
    #[test]
    fn test_parse_file_content_json() {
        let tmp = write_json_file(SINGLE_EVENT_JSON);

        let (sha256, records) =
            parse_file_content(tmp.path()).expect("parse_file_content should succeed");

        assert!(!sha256.is_empty(), "sha256 must not be empty");
        assert_eq!(sha256.len(), 64, "SHA-256 hex digest is 64 chars");
        assert_eq!(records.len(), 1, "one record in the file");
        assert_eq!(records[0].event_name, "DescribeInstances");
    }

    // Test #26: parse_file_content correctly reads and parses a .json.gz file.
    #[test]
    fn test_parse_file_content_gz() {
        let tmp = write_gz_file(SINGLE_EVENT_JSON);

        let (sha256, records) =
            parse_file_content(tmp.path()).expect("parse_file_content should handle .gz");

        assert_eq!(sha256.len(), 64);
        assert_eq!(records.len(), 1);
    }
}
