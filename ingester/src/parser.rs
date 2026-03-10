//! CloudTrail JSON log parser.
//!
//! Parses AWS CloudTrail log files (JSON format) into typed Rust structs.

use anyhow::{Context, Result};
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
///
/// CloudTrail log files contain a top-level `Records` array.
#[derive(Debug, Deserialize)]
pub struct CloudTrailLog {
    #[serde(rename = "Records")]
    pub records: Vec<CloudTrailEvent>,
}

/// Parse a CloudTrail JSON string into a [`CloudTrailLog`].
///
/// Returns an error if the input is not valid JSON or does not conform
/// to the expected CloudTrail log structure.
pub fn parse_cloudtrail_log(json: &str) -> Result<CloudTrailLog> {
    serde_json::from_str(json).with_context(|| "Failed to parse CloudTrail log JSON")
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
        assert!(event.user_identity.is_none());
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
