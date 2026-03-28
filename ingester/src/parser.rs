//! CloudTrail JSON log parser.
//!
//! Parses AWS CloudTrail log files (JSON format) into typed Rust structs.
//!
//! ## Two-step parsing strategy
//!
//! Parsing uses a two-step strategy to eliminate expensive round-trip
//! JSON serialization:
//!
//! 1. **Tokenise** the outer `{"Records": [...]}` envelope with
//!    `serde_json::RawValue` to locate per-record byte ranges without
//!    building any `serde_json::Value` trees.
//! 2. **Parse** each record individually into [`RawCloudTrailEvent`],
//!    keeping `requestParameters` and `responseElements` as raw JSON
//!    (`Box<RawValue>`) so that the insert path can write them directly.
//!
//! Compared to the old single-pass approach, this eliminates:
//! - `serde_json::Value` tree allocation for req/resp objects.
//! - The per-event `serde_json::to_string(event)` call (re-serialisation).
//! - `serde_json::Value::to_string()` calls for req/resp at insert time.
//! - `serde_json::Value` tree traversal for `userIdentity` at insert time.

use anyhow::{Context, Result};
use serde::Deserialize;
use serde_json::value::RawValue;

// ─── Internal serde helpers ──────────────────────────────────────────────────

/// Minimal deserialization struct for the `userIdentity` sub-object.
///
/// Only the three columns stored in the DB are captured; all other keys
/// are ignored. This avoids building a full `serde_json::Value` tree for
/// the identity object.
#[derive(Deserialize)]
struct UserIdentityDeser {
    #[serde(rename = "type")]
    identity_type: Option<String>,
    arn: Option<String>,
    #[serde(rename = "accountId")]
    account_id: Option<String>,
}

/// Internal deserialization struct for a single CloudTrail event record.
///
/// `requestParameters` and `responseElements` are deserialized as
/// `Box<RawValue>` (raw JSON byte slices) rather than `serde_json::Value`
/// trees, avoiding heap allocations for all nested objects and making the
/// later `.get().to_owned()` copy far cheaper than `Value::to_string()`.
#[derive(Deserialize)]
struct RawCloudTrailEvent {
    #[serde(rename = "eventTime", default)]
    event_time: Option<String>,
    #[serde(rename = "eventName", default)]
    event_name: Option<String>,
    #[serde(rename = "eventSource", default)]
    event_source: Option<String>,
    #[serde(rename = "awsRegion", default)]
    aws_region: Option<String>,
    #[serde(rename = "sourceIPAddress")]
    source_ip_address: Option<String>,
    #[serde(rename = "userAgent")]
    user_agent: Option<String>,
    /// Parsed into a small typed struct — no full Value tree.
    #[serde(rename = "userIdentity")]
    user_identity: Option<UserIdentityDeser>,
    /// Raw JSON — avoids `serde_json::Value` tree allocation entirely.
    #[serde(rename = "requestParameters")]
    request_parameters: Option<Box<RawValue>>,
    /// Raw JSON — avoids `serde_json::Value` tree allocation entirely.
    #[serde(rename = "responseElements")]
    response_elements: Option<Box<RawValue>>,
    #[serde(rename = "errorCode")]
    error_code: Option<String>,
    #[serde(rename = "errorMessage")]
    error_message: Option<String>,
    #[serde(rename = "readOnly")]
    read_only: Option<bool>,
    #[serde(rename = "eventType")]
    event_type: Option<String>,
    #[serde(rename = "recipientAccountId")]
    recipient_account_id: Option<String>,
}

/// Fast outer envelope: locates record boundaries without parsing values.
#[derive(Deserialize)]
struct CloudTrailLogRaw {
    #[serde(rename = "Records")]
    records: Vec<Box<RawValue>>,
}

// ─── Public API ──────────────────────────────────────────────────────────────

/// Pre-extracted fields from the `userIdentity` sub-object of a CloudTrail event.
///
/// Grouping these three columns into their own struct improves readability and
/// makes it clear they share a common origin.
#[derive(Debug, Clone, Default)]
pub struct UserIdentity {
    /// Value of `userIdentity.type`.
    pub identity_type: Option<String>,
    /// Value of `userIdentity.arn`.
    pub arn: Option<String>,
    /// Value of `userIdentity.accountId`.
    pub account_id: Option<String>,
}

/// A single CloudTrail event record.
///
/// ### Performance notes
///
/// - `raw_json`: original JSON bytes of this record.  Written directly to the
///   `raw_event` DB column — eliminates the `serde_json::to_string(event)`
///   round-trip that was previously required for every event.
/// - `request_parameters` / `response_elements`: raw JSON strings captured
///   during parsing.  Written directly to the DB — eliminates
///   `serde_json::Value::to_string()` at insert time.
/// - `user_identity`: pre-extracted during parsing — eliminates
///   `serde_json::Value` tree traversal at insert time.
#[derive(Debug, Clone)]
pub struct CloudTrailEvent {
    pub event_time: String,
    pub event_name: String,
    pub event_source: String,
    pub aws_region: String,
    pub source_ip_address: Option<String>,
    pub user_agent: Option<String>,
    /// Pre-extracted from the `userIdentity` sub-object.
    pub user_identity: UserIdentity,
    /// Raw JSON string of the original `requestParameters` object.
    pub request_parameters: Option<String>,
    /// Raw JSON string of the original `responseElements` object.
    pub response_elements: Option<String>,
    pub error_code: Option<String>,
    pub error_message: Option<String>,
    pub read_only: Option<bool>,
    pub event_type: Option<String>,
    pub recipient_account_id: Option<String>,
    /// Original JSON bytes of this record — written directly to `raw_event`.
    pub raw_json: String,
}

/// Wrapper for the CloudTrail JSON file format.
///
/// CloudTrail log files contain a top-level `Records` array.
#[derive(Debug)]
pub struct CloudTrailLog {
    pub records: Vec<CloudTrailEvent>,
}

/// Parse a CloudTrail JSON string into a [`CloudTrailLog`].
///
/// Uses the two-step strategy described in the module documentation.
/// Returns an error if the input is not valid JSON or does not conform
/// to the expected CloudTrail log structure.
pub fn parse_cloudtrail_log(json: &str) -> Result<CloudTrailLog> {
    // Step 1: fast tokenisation — locate record boundaries without building
    // any serde_json::Value trees.
    let raw_log: CloudTrailLogRaw =
        serde_json::from_str(json).with_context(|| "Failed to parse CloudTrail log JSON")?;

    let mut records = Vec::with_capacity(raw_log.records.len());

    // Step 2: parse each record individually.
    for raw_record in raw_log.records {
        let raw_str = raw_record.get(); // &str into the original json buffer

        let ev: RawCloudTrailEvent = serde_json::from_str(raw_str)
            .with_context(|| "Failed to parse CloudTrail event record")?;

        // Destructure the small userIdentity struct to avoid Value traversal
        // at insert time.
        let (ui_type, ui_arn, ui_account_id) = match ev.user_identity {
            Some(ui) => (ui.identity_type, ui.arn, ui.account_id),
            None => (None, None, None),
        };

        records.push(CloudTrailEvent {
            event_time: ev.event_time.unwrap_or_default(),
            event_name: ev.event_name.unwrap_or_default(),
            event_source: ev.event_source.unwrap_or_default(),
            aws_region: ev.aws_region.unwrap_or_default(),
            source_ip_address: ev.source_ip_address,
            user_agent: ev.user_agent,
            user_identity: UserIdentity {
                identity_type: ui_type,
                arn: ui_arn,
                account_id: ui_account_id,
            },
            // `RawValue::get()` yields a &str pointing into the record's raw
            // bytes; `.to_owned()` copies them into an owned String — much
            // cheaper than serialising a `serde_json::Value` tree.
            request_parameters: ev.request_parameters.map(|v| v.get().to_owned()),
            response_elements: ev.response_elements.map(|v| v.get().to_owned()),
            error_code: ev.error_code,
            error_message: ev.error_message,
            read_only: ev.read_only,
            event_type: ev.event_type,
            recipient_account_id: ev.recipient_account_id,
            // Preserve the original JSON bytes so the insert path can write
            // `raw_event` without any re-serialisation.
            raw_json: raw_str.to_owned(),
        });
    }

    Ok(CloudTrailLog { records })
}

#[cfg(test)]
mod tests {
    use super::*;

    // Test #1: Parse a minimal CloudTrail JSON record into a struct.
    #[test]
    fn test_parse_single_cloudtrail_event() {
        let json = r#"{
            "Records": [
                {
                    "eventTime": "2024-01-15T10:30:00Z",
                    "eventName": "DescribeInstances",
                    "eventSource": "ec2.amazonaws.com",
                    "awsRegion": "us-east-1",
                    "sourceIPAddress": "198.51.100.1",
                    "userAgent": "aws-cli/2.0",
                    "readOnly": true,
                    "eventType": "AwsApiCall",
                    "recipientAccountId": "123456789012"
                }
            ]
        }"#;

        let log = parse_cloudtrail_log(json).expect("Should parse successfully");

        assert_eq!(log.records.len(), 1);
        let event = &log.records[0];
        assert_eq!(event.event_time, "2024-01-15T10:30:00Z");
        assert_eq!(event.event_name, "DescribeInstances");
        assert_eq!(event.event_source, "ec2.amazonaws.com");
        assert_eq!(event.aws_region, "us-east-1");
        assert_eq!(event.source_ip_address.as_deref(), Some("198.51.100.1"));
        assert_eq!(event.user_agent.as_deref(), Some("aws-cli/2.0"));
        assert_eq!(event.read_only, Some(true));
    }

    // Test #2: Parse a CloudTrail file containing `{"Records": [...]}` with multiple events.
    #[test]
    fn test_parse_cloudtrail_records_array() {
        let json = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/testdata/multi_event.json"
        ))
        .expect("testdata file should exist");

        let log = parse_cloudtrail_log(&json).expect("Should parse successfully");

        assert_eq!(log.records.len(), 3);
        assert_eq!(log.records[0].event_name, "DescribeInstances");
        assert_eq!(log.records[1].event_name, "CreateBucket");
        assert_eq!(log.records[2].event_name, "AssumeRole");
    }

    // Test #3: Fields like `errorCode` may be absent; parse should not panic.
    #[test]
    fn test_parse_handles_missing_optional_fields() {
        // Minimal event with only required fields; all optional fields absent.
        let json = r#"{
            "Records": [
                {
                    "eventTime": "2024-01-15T10:30:00Z",
                    "eventName": "DescribeInstances",
                    "eventSource": "ec2.amazonaws.com",
                    "awsRegion": "us-east-1"
                }
            ]
        }"#;

        let log = parse_cloudtrail_log(json).expect("Should parse successfully");

        let event = &log.records[0];
        assert!(event.source_ip_address.is_none());
        assert!(event.user_agent.is_none());
        // userIdentity sub-fields are pre-extracted; all should be None here.
        assert!(event.user_identity.identity_type.is_none());
        assert!(event.user_identity.arn.is_none());
        assert!(event.user_identity.account_id.is_none());
        assert!(event.request_parameters.is_none());
        assert!(event.response_elements.is_none());
        assert!(event.error_code.is_none());
        assert!(event.error_message.is_none());
        assert!(event.read_only.is_none());
        assert!(event.event_type.is_none());
        assert!(event.recipient_account_id.is_none());
    }

    // Test #4: Invalid JSON input returns an appropriate error.
    #[test]
    fn test_parse_malformed_json_returns_error() {
        let json = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/testdata/malformed.json"
        ))
        .expect("testdata file should exist");

        let result = parse_cloudtrail_log(&json);

        assert!(result.is_err(), "Malformed JSON should return an error");
    }

    // Test #5: `{"Records": []}` returns an empty vec, not an error.
    #[test]
    fn test_parse_empty_records_array() {
        let json = r#"{"Records": []}"#;

        let log = parse_cloudtrail_log(json).expect("Should parse successfully");

        assert_eq!(log.records.len(), 0);
    }
}
