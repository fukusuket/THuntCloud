//! THuntCloud ingester library.
//!
//! Provides the public API for ingesting AWS CloudTrail log files into DuckDB.

pub mod db;
pub mod decompressor;
pub mod ingest;
pub mod parser;
pub mod progress;
