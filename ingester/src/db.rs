//! DuckDB connection, table schema management, and batch insert operations.
//!
//! This module is the only place that writes to DuckDB. All other modules
//! interact with the database through the public API defined here.

use std::collections::HashMap;

use anyhow::{Context, Result};
use duckdb::{Appender, Connection, ToSql};

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

/// Append a single [`CloudTrailEvent`] row (with pre-resolved [`GeoInfo`]) to an open
/// [`Appender`].
///
/// This is the single source of truth for the 24-column row layout.
/// Both [`insert_events_with_geo`] and any future bulk-append callers must use
/// this helper so that schema changes only need to be made in one place.
fn append_event_row(
    appender: &mut Appender<'_>,
    event: &CloudTrailEvent,
    geo: &GeoInfo,
) -> Result<()> {
    // All JSON fields are pre-computed strings on CloudTrailEvent —
    // no serde_json serialisation occurs in this hot path.
    let params: Vec<&dyn ToSql> = vec![
        &event.event_time,                  // event_time               TIMESTAMP
        &event.event_name,                  // event_name               VARCHAR
        &event.event_source,                // event_source             VARCHAR
        &event.aws_region,                  // aws_region               VARCHAR
        &event.source_ip_address,           // source_ip_address        VARCHAR (Option)
        &event.user_agent,                  // user_agent               VARCHAR (Option)
        &event.user_identity.identity_type, // user_identity_type       VARCHAR (Option)
        &event.user_identity.arn,           // user_identity_arn        VARCHAR (Option)
        &event.user_identity.account_id,    // user_identity_account_id VARCHAR (Option)
        &event.request_parameters,          // request_parameters       VARCHAR (Option<String>)
        &event.response_elements,           // response_elements        VARCHAR (Option<String>)
        &event.error_code,                  // error_code               VARCHAR (Option)
        &event.error_message,               // error_message            VARCHAR (Option)
        &event.read_only,                   // read_only                BOOLEAN (Option)
        &event.event_type,                  // event_type               VARCHAR (Option)
        &event.recipient_account_id,        // recipient_account_id     VARCHAR (Option)
        &event.raw_json,                    // raw_event                VARCHAR (original JSON)
        &geo.country_code,                  // geo_country_code         VARCHAR (Option)
        &geo.country_name,                  // geo_country_name         VARCHAR (Option)
        &geo.city,                          // geo_city                 VARCHAR (Option)
        &geo.latitude,                      // geo_latitude             DOUBLE  (Option)
        &geo.longitude,                     // geo_longitude            DOUBLE  (Option)
        &geo.asn,                           // geo_asn                  VARCHAR (Option)
        &geo.org,                           // geo_org                  VARCHAR (Option)
    ];
    appender
        .append_row(params.as_slice())
        .context("Failed to append event row")
}

/// Insert a slice of [`CloudTrailEvent`]s with optional GeoIP enrichment.
///
/// Uses [`duckdb::Appender`] for high-throughput batch inserts.
/// When `geoip` is `None`, all geo columns are written as `NULL`.
/// Returns the number of rows inserted.
///
/// All fields that were previously re-serialised at insert time
/// (`raw_event`, `request_parameters`, `response_elements`) are now
/// stored as pre-computed strings on [`CloudTrailEvent`], so this
/// function performs zero JSON serialisation.
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
        // Look up geo info for the source IP (or return all-None when no enricher).
        let geo: GeoInfo = match (geoip, &event.source_ip_address) {
            (Some(enricher), Some(ip)) => enricher.lookup(ip),
            _ => GeoInfo::all_none(),
        };
        append_event_row(&mut appender, event, &geo)?;
    }

    appender.flush().context("Failed to flush appender")?;
    Ok(events.len())
}

/// Record a batch of ingested files in a single Appender flush.
///
/// Replaces N individual `INSERT OR REPLACE` statements (one per file) with
/// a single Appender write, reducing SQL round-trip overhead from O(N) to
/// O(1) per chunk.
///
/// `ingested_at` is supplied as a formatted RFC 3339 timestamp string so the
/// appender can fill the TIMESTAMP column without relying on SQL DEFAULT.
pub fn batch_mark_ingested(conn: &Connection, files: &[(String, String)]) -> Result<()> {
    if files.is_empty() {
        return Ok(());
    }
    let now = chrono::Utc::now()
        .format("%Y-%m-%d %H:%M:%S%.6f")
        .to_string();
    let mut appender = conn
        .appender("ingested_files")
        .context("Failed to create appender for ingested_files")?;
    for (path, sha256) in files {
        appender
            .append_row([path.as_str(), sha256.as_str(), now.as_str()])
            .with_context(|| format!("Failed to append ingested_files row for {path}"))?;
    }
    appender
        .flush()
        .context("Failed to flush ingested_files appender")?;
    Ok(())
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
    use crate::test_util::{full_event, make_enricher, minimal_event, setup_db, temp_db};

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
        let enricher = make_enricher();

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
        assert!(
            cc.is_none(),
            "geo_country_code should be NULL without enricher"
        );
        assert!(
            cn.is_none(),
            "geo_country_name should be NULL without enricher"
        );
        assert!(city.is_none(), "geo_city should be NULL without enricher");
    }

    // Test D-05: Private IPs are stored with the "PRIVATE" marker.
    #[test]
    fn test_insert_events_private_ip_stores_marker() {
        let enricher = make_enricher();

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
