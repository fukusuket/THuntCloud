//! DuckDB connection, table schema management, and batch insert operations.
//!
//! This module is the only place that writes to DuckDB. All other modules
//! interact with the database through the public API defined here.

use std::collections::HashMap;

use anyhow::{Context, Result};
use duckdb::{Connection, ToSql};

use crate::geoip::{GeoInfo, GeoipEnricher};
use crate::parser::CloudTrailEvent;

/// Create the `cloudtrail_events` and `ingested_files` tables if they do not exist,
/// then ensure the 7 geo-enrichment columns are present.
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
            request_parameters       VARCHAR,
            response_elements        VARCHAR,
            error_code               VARCHAR,
            error_message            VARCHAR,
            read_only                BOOLEAN,
            event_type               VARCHAR,
            recipient_account_id     VARCHAR,
            raw_event                VARCHAR
        );

        CREATE TABLE IF NOT EXISTS ingested_files (
            file_path   VARCHAR PRIMARY KEY,
            sha256      VARCHAR NOT NULL,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        ",
    )
    .context("Failed to create database tables")?;

    ensure_geo_columns(conn)
}

/// Add the 7 geo-enrichment columns to `cloudtrail_events` if they do not exist.
///
/// Uses `ALTER TABLE … ADD COLUMN IF NOT EXISTS` — safe to call repeatedly.
pub fn ensure_geo_columns(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_country_code VARCHAR;
        ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_country_name VARCHAR;
        ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_city         VARCHAR;
        ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_latitude     DOUBLE;
        ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_longitude    DOUBLE;
        ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_asn          VARCHAR;
        ALTER TABLE cloudtrail_events ADD COLUMN IF NOT EXISTS geo_org          VARCHAR;
        ",
    )
    .context("Failed to add geo columns to cloudtrail_events")
}

/// Insert a slice of [`CloudTrailEvent`]s with optional GeoIP enrichment.
///
/// Uses [`duckdb::Appender`] for high-throughput batch inserts.
/// When `geoip` is `None`, all geo columns are written as `NULL`.
/// Returns the number of rows inserted.
pub fn insert_events_with_geo(
    conn: &Connection,
    events: &[CloudTrailEvent],
    geoip: Option<&GeoipEnricher>,
) -> Result<usize> {
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

        // Look up geo info for the source IP (or return all-None when no enricher).
        let geo: GeoInfo = match (geoip, &event.source_ip_address) {
            (Some(enricher), Some(ip)) => enricher.lookup(ip),
            _ => GeoInfo::all_none(),
        };

        // Build a slice of trait-object references for the 24-column table.
        let params: Vec<&dyn ToSql> = vec![
            &event.event_time,           // event_time               TIMESTAMP
            &event.event_name,           // event_name               VARCHAR
            &event.event_source,         // event_source             VARCHAR
            &event.aws_region,           // aws_region               VARCHAR
            &event.source_ip_address,    // source_ip_address        VARCHAR (Option)
            &event.user_agent,           // user_agent               VARCHAR (Option)
            &ui_type,                    // user_identity_type       VARCHAR (Option)
            &ui_arn,                     // user_identity_arn        VARCHAR (Option)
            &ui_account_id,              // user_identity_account_id VARCHAR (Option)
            &req_params,                 // request_parameters       VARCHAR (Option<String>)
            &resp_elements,              // response_elements        VARCHAR (Option<String>)
            &event.error_code,           // error_code               VARCHAR (Option)
            &event.error_message,        // error_message            VARCHAR (Option)
            &event.read_only,            // read_only                BOOLEAN (Option)
            &event.event_type,           // event_type               VARCHAR (Option)
            &event.recipient_account_id, // recipient_account_id     VARCHAR (Option)
            &raw_event,                  // raw_event                VARCHAR (JSON string)
            &geo.country_code,           // geo_country_code         VARCHAR (Option)
            &geo.country_name,           // geo_country_name         VARCHAR (Option)
            &geo.city,                   // geo_city                 VARCHAR (Option)
            &geo.latitude,               // geo_latitude             DOUBLE  (Option)
            &geo.longitude,              // geo_longitude            DOUBLE  (Option)
            &geo.asn,                    // geo_asn                  VARCHAR (Option)
            &geo.org,                    // geo_org                  VARCHAR (Option)
        ];

        appender
            .append_row(params.as_slice())
            .context("Failed to append event row")?;
    }

    appender.flush().context("Failed to flush appender")?;
    Ok(events.len())
}

/// Load the entire `ingested_files` table into a `HashMap<file_path, sha256>`.
///
/// Using this function at the start of an ingestion run replaces the previous
/// pattern of one `SELECT` per file with a single bulk query, which is orders
/// of magnitude faster when tens of thousands of files are already tracked.
///
/// The caller is expected to update the map as new files are inserted so that
/// within-run duplicate detection works correctly without extra DB round-trips.
pub fn fetch_ingested_files_map(conn: &Connection) -> Result<HashMap<String, String>> {
    let mut stmt = conn
        .prepare("SELECT file_path, sha256 FROM ingested_files")
        .context("Failed to prepare ingested_files query")?;
    let rows = stmt
        .query_map([], |row| {
            let path: String = row.get(0)?;
            let sha256: String = row.get(1)?;
            Ok((path, sha256))
        })
        .context("Failed to query ingested_files")?;
    let mut map = HashMap::new();
    for row in rows {
        let (path, sha256) = row.context("Failed to read ingested_files row")?;
        map.insert(path, sha256);
    }
    Ok(map)
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
        let inserted =
            insert_events_with_geo(&conn, &[event], None).expect("insert should succeed");

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
        let inserted =
            insert_events_with_geo(&conn, &events, None).expect("batch insert should succeed");

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
        let inserted = insert_events_with_geo(&conn, &[event], None)
            .expect("insert with null fields should succeed");
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

    // Test D-01: ensure_geo_columns adds 7 new columns to cloudtrail_events.
    #[test]
    fn test_ensure_geo_columns_adds_seven_columns() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        // Verify all 7 geo columns exist via information_schema (works on empty table).
        let geo_col_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM information_schema.columns \
                 WHERE table_name = 'cloudtrail_events' AND column_name LIKE 'geo_%'",
                [],
                |row| row.get(0),
            )
            .expect("information_schema query should succeed");
        assert_eq!(geo_col_count, 7, "should have exactly 7 geo_ columns");
    }

    // Test D-02: ensure_geo_columns is idempotent.
    #[test]
    fn test_ensure_geo_columns_is_idempotent() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        ensure_geo_columns(&conn).expect("second call to ensure_geo_columns should succeed");
        ensure_geo_columns(&conn).expect("third call to ensure_geo_columns should also succeed");
    }

    // Test D-03: insert_events_with_geo stores geo data when GeoInfo is provided.
    #[test]
    fn test_insert_events_with_geo_populates_columns() {
        use crate::geoip::GeoipConfig;
        use crate::geoip::GeoipEnricher;
        use std::path::PathBuf;

        let city_db = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/testdata/geoip/GeoLite2-City-Test.mmdb");
        let config = GeoipConfig {
            city_db_path: Some(city_db),
            country_db_path: None,
            asn_db_path: None,
        };
        let enricher = GeoipEnricher::open(&config).expect("should open test mmdb");

        let conn = temp_db();
        ensure_table(&conn).unwrap();

        // Use a known IP from the test mmdb: 81.2.69.160 → GB / London.
        let mut event = full_event();
        event.source_ip_address = Some("81.2.69.160".to_string());

        insert_events_with_geo(&conn, &[event], Some(&enricher))
            .expect("insert with geo should succeed");

        let country_code: Option<String> = conn
            .query_row(
                "SELECT geo_country_code FROM cloudtrail_events LIMIT 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(
            country_code.as_deref(),
            Some("GB"),
            "geo_country_code should be GB for 81.2.69.160"
        );
    }

    // Test D-04: insert_events_with_geo stores NULL geo columns when no enricher.
    #[test]
    fn test_insert_events_without_geo_columns_are_null() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        let event = full_event();
        insert_events_with_geo(&conn, &[event], None).expect("insert without geo should succeed");

        let (cc, cn, city): (Option<String>, Option<String>, Option<String>) = conn
            .query_row(
                "SELECT geo_country_code, geo_country_name, geo_city FROM cloudtrail_events LIMIT 1",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert!(cc.is_none(), "geo_country_code should be NULL without enricher");
        assert!(cn.is_none(), "geo_country_name should be NULL without enricher");
        assert!(city.is_none(), "geo_city should be NULL without enricher");
    }

    // Test D-05: Private IPs are stored with the "PRIVATE" marker.
    #[test]
    fn test_insert_events_private_ip_stores_marker() {
        use crate::geoip::GeoipConfig;
        use crate::geoip::GeoipEnricher;
        use std::path::PathBuf;

        let city_db = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/testdata/geoip/GeoLite2-City-Test.mmdb");
        let config = GeoipConfig {
            city_db_path: Some(city_db),
            country_db_path: None,
            asn_db_path: None,
        };
        let enricher = GeoipEnricher::open(&config).expect("should open test mmdb");

        let conn = temp_db();
        ensure_table(&conn).unwrap();

        let mut event = full_event();
        event.source_ip_address = Some("10.0.0.1".to_string());

        insert_events_with_geo(&conn, &[event], Some(&enricher))
            .expect("insert with private IP should succeed");

        let country_code: Option<String> = conn
            .query_row(
                "SELECT geo_country_code FROM cloudtrail_events LIMIT 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(
            country_code.as_deref(),
            Some("PRIVATE"),
            "geo_country_code should be PRIVATE for 10.0.0.1"
        );
    }

    // Test #37: fetch_ingested_files_map returns an empty map when no files have been ingested.
    #[test]
    fn test_fetch_ingested_files_map_empty() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        let map = fetch_ingested_files_map(&conn).expect("fetch should succeed on empty table");
        assert!(
            map.is_empty(),
            "map must be empty when ingested_files is empty"
        );
    }

    // Test #38: fetch_ingested_files_map returns all entries present in ingested_files.
    #[test]
    fn test_fetch_ingested_files_map_with_entries() {
        let conn = temp_db();
        ensure_table(&conn).unwrap();

        conn.execute(
            "INSERT INTO ingested_files (file_path, sha256) VALUES (?, ?)",
            duckdb::params!["/logs/a.json", "aaaa1111"],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO ingested_files (file_path, sha256) VALUES (?, ?)",
            duckdb::params!["/logs/b.json.gz", "bbbb2222"],
        )
        .unwrap();

        let map = fetch_ingested_files_map(&conn).expect("fetch should succeed");
        assert_eq!(map.len(), 2, "map must contain both entries");
        assert_eq!(
            map.get("/logs/a.json").map(String::as_str),
            Some("aaaa1111")
        );
        assert_eq!(
            map.get("/logs/b.json.gz").map(String::as_str),
            Some("bbbb2222")
        );
    }
}
