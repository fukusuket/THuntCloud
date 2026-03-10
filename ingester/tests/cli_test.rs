//! CLI integration tests for the ingester binary.
//!
//! These tests exercise the command-line interface end-to-end using
//! `assert_cmd`. The binary must be built before running these tests.

use assert_cmd::cargo_bin_cmd;
use predicates::prelude::*;
use std::io::Write;
use tempfile::{NamedTempFile, TempDir};

/// Write a minimal CloudTrail JSON file and return the temp file handle.
fn write_single_event_json() -> NamedTempFile {
    let mut tmp = tempfile::Builder::new().suffix(".json").tempfile().unwrap();
    tmp.write_all(
        br#"{
        "Records": [{
            "eventTime": "2024-01-15T10:30:00Z",
            "eventName": "DescribeInstances",
            "eventSource": "ec2.amazonaws.com",
            "awsRegion": "us-east-1"
        }]
    }"#,
    )
    .unwrap();
    tmp.flush().unwrap();
    tmp
}

// Test #20: Running `ingester ingest --path <dir>` exits successfully and
//           prints a summary that includes the records_inserted count.
#[test]
fn test_cli_ingest_command() {
    let log_file = write_single_event_json();
    let db_dir = TempDir::new().unwrap();
    let db_path = db_dir.path().join("test.db");

    cargo_bin_cmd!("ingester")
        .args([
            "ingest",
            "--path",
            log_file.path().to_str().unwrap(),
            "--db",
            db_path.to_str().unwrap(),
        ])
        .assert()
        .success()
        .stdout(predicate::str::contains("records_inserted"));
}

// Test #21: Running without `--path` produces a usage error (non-zero exit)
//           and the error message appears on stderr.
#[test]
fn test_cli_missing_path_shows_error() {
    let db_dir = TempDir::new().unwrap();
    let db_path = db_dir.path().join("test.db");

    cargo_bin_cmd!("ingester")
        .args(["ingest", "--db", db_path.to_str().unwrap()])
        .assert()
        .failure()
        .stderr(predicate::str::contains("error"));
}
