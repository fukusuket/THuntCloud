//! DuckDB connection, table schema management, and batch insert operations.
//!
//! This module is the only place that writes to DuckDB. All other modules
//! interact with the database through the public API defined here.

use anyhow::{Context, Result};
use duckdb::{Connection, ToSql};

use crate::parser::CloudTrailEvent;

/// Create the `cloudtrail_events` and `ingested_files` tables if they do not exist.
///
/// This function is idempotent — calling it multiple times on the same
/// connection is safe.
pub fn ensure_table(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS cloudtrail_events (
            event_time               TIMESTAMP,
            event_name               VARCHAR,
            event_source             VARCHAR,
            aws_region               VARCHAR,
            source_ip_address        VARCHAR,
            user_agent               VARCHAR,
            user_identity_type       VARCHAR,
            user_identity_arn        VARCHAR,
            user_identity_account_id VARCHAR,
            request_parameters       JSON,
            response_elements        JSON,
            error_code               VARCHAR,
            error_message            VARCHAR,
            read_only                BOOLEAN,
            event_type               VARCHAR,
            recipient_account_id     VARCHAR,
            raw_event                JSON
        );

        CREATE TABLE IF NOT EXISTS ingested_files (
            file_path   VARCHAR PRIMARY KEY,
            sha256      VARCHAR NOT NULL,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        ",
    )
    .context("Failed to create database tables")
}

/// Insert a slice of [`CloudTrailEvent`]s into the `cloudtrail_events` table.
///
/// Uses [`duckdb::Appender`] for high-throughput batch inserts.
/// Returns the number of rows inserted.
pub fn insert_events(conn: &Connection, events: &[CloudTrailEvent]) -> Result<usize> {
    if events.is_empty() {
        return Ok(0);
    }

    let mut appender = conn
        .appender("cloudtrail_events")
        .context("Failed to create appender for cloudtrail_events")?;

    for event in events {
        let raw_event =
            serde_json::to_string(event).context("Failed to serialize event to JSON")?;

        // Extract nested userIdentity fields, gracefully handling missing values.
        let ui = event.user_identity.as_ref();
        let ui_type = ui.and_then(|v| v.get("type")).and_then(|v| v.as_str());
        let ui_arn = ui.and_then(|v| v.get("arn")).and_then(|v| v.as_str());
        let ui_account_id = ui.and_then(|v| v.get("accountId")).and_then(|v| v.as_str());

        let req_params = event.request_parameters.as_ref().map(|v| v.to_string());
        let resp_elements = event.response_elements.as_ref().map(|v| v.to_string());

        // Build a slice of trait-object references for the 17-column table.
        // Using Vec<&dyn ToSql> keeps the code maintainable as columns change.
        let params: Vec<&dyn ToSql> = vec![
            &event.event_time,           // event_time       TIMESTAMP  (auto-cast from &str)
            &event.event_name,           // event_name       VARCHAR
            &event.event_source,         // event_source     VARCHAR
            &event.aws_region,           // aws_region       VARCHAR
            &event.source_ip_address,    // source_ip_address VARCHAR (Option)
            &event.user_agent,           // user_agent        VARCHAR (Option)
            &ui_type,                    // user_identity_type VARCHAR (Option)
            &ui_arn,                     // user_identity_arn  VARCHAR (Option)
            &ui_account_id,              // user_identity_account_id VARCHAR (Option)
            &req_params,                 // request_parameters JSON (Option<String>)
            &resp_elements,              // response_elements  JSON (Option<String>)
            &event.error_code,           // error_code         VARCHAR (Option)
            &event.error_message,        // error_message      VARCHAR (Option)
            &event.read_only,            // read_only          BOOLEAN (Option)
            &event.event_type,           // event_type         VARCHAR (Option)
            &event.recipient_account_id, // recipient_account_id VARCHAR (Option)
            &raw_event,                  // raw_event          JSON
        ];

        appender
            .append_row(params.as_slice())
            .context("Failed to append event row")?;
    }

    appender.flush().context("Failed to flush appender")?;
    Ok(events.len())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::CloudTrailEvent;

    /// Open an in-memory DuckDB connection for testing.
    fn temp_db() -> Connection {
        Connection::open_in_memory().unwrap()
    }

    /// Build a minimal [`CloudTrailEvent`] with all required fields set and
    /// all optional fields set to `None`.
    fn minimal_event() -> CloudTrailEvent {
        CloudTrailEvent {
            event_time: "2024-01-15T10:30:00Z".to_string(),
            event_name: "DescribeInstances".to_string(),
            event_source: "ec2.amazonaws.com".to_string(),
            aws_region: "us-east-1".to_string(),
            source_ip_address: None,
            user_agent: None,
            user_identity: None,
            request_parameters: None,
            response_elements: None,
            error_code: None,
            error_message: None,
            read_only: None,
            event_type: None,
            recipient_account_id: None,
        }
    }

    /// Build a fully-populated [`CloudTrailEvent`] with all optional fields set.
    fn full_event() -> CloudTrailEvent {
        CloudTrailEvent {
            event_time: "2024-01-15T10:30:00Z".to_string(),
            event_name: "DescribeInstances".to_string(),
            event_source: "ec2.amazonaws.com".to_string(),
            aws_region: "us-east-1".to_string(),
            source_ip_address: Some("198.51.100.1".to_string()),
            user_agent: Some("aws-cli/2.0".to_string()),
            user_identity: Some(serde_json::json!({
                "type": "IAMUser",
                "arn": "arn:aws:iam::123456789012:user/testuser",
                "accountId": "123456789012"
            })),
            request_parameters: Some(serde_json::json!({"key": "value"})),
            response_elements: Some(serde_json::json!({"result": "ok"})),
            error_code: None,
            error_message: None,
            read_only: Some(true),
            event_type: Some("AwsApiCall".to_string()),
            recipient_account_id: Some("123456789012".to_string()),
        }
    }

    // Test #9: `ensure_table()` creates the `cloudtrail_events` table in a temp DuckDB.
    #[test]
    fn test_create_cloudtrail_table() {
        let conn = temp_db();

        ensure_table(&conn).expect("ensure_table should succeed");

        // Verify the table exists by querying its row count.
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM cloudtrail_events", [], |row| {
                row.get(0)
            })
            .expect("cloudtrail_events table should exist and be queryable");
        assert_eq!(count, 0);

        // Verify the ingested_files table also exists.
        let count2: i64 = conn
            .query_row("SELECT COUNT(*) FROM ingested_files", [], |row| row.get(0))
            .expect("ingested_files table should exist and be queryable");
        assert_eq!(count2, 0);
    }

    // Test #10: Calling `ensure_table()` twice does not error.
    #[test]
    fn test_create_table_is_idempotent() {
        let conn = temp_db();

        ensure_table(&conn).expect("First call should succeed");
        ensure_table(&conn).expect("Second call should also succeed without error");
    }

    // Test #11: Insert one parsed event and verify it can be queried back.
    #[test]
    fn test_insert_single_event() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        let event = full_event();
        let inserted = insert_events(&conn, &[event]).expect("insert_events should succeed");

        assert_eq!(inserted, 1);

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM cloudtrail_events", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(count, 1);

        // Spot-check a column value.
        let name: String = conn
            .query_row(
                "SELECT event_name FROM cloudtrail_events LIMIT 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(name, "DescribeInstances");
    }

    // Test #12: Insert 100 events in a batch and verify the row count.
    #[test]
    fn test_insert_batch_events() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        let events: Vec<CloudTrailEvent> = (0..100).map(|_| full_event()).collect();
        let inserted = insert_events(&conn, &events).expect("batch insert should succeed");

        assert_eq!(inserted, 100);

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM cloudtrail_events", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(count, 100);
    }

    // Test #13: Events with `None` optional fields are inserted without error.
    #[test]
    fn test_insert_event_with_null_fields() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        // minimal_event() has all optional fields set to None.
        let event = minimal_event();
        let inserted =
            insert_events(&conn, &[event]).expect("insert with null fields should succeed");
        assert_eq!(inserted, 1);

        // Verify the NULL columns are actually NULL in the database.
        let (src_ip, error_code): (Option<String>, Option<String>) = conn
            .query_row(
                "SELECT source_ip_address, error_code FROM cloudtrail_events LIMIT 1",
                [],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .unwrap();
        assert!(src_ip.is_none());
        assert!(error_code.is_none());
    }
}
