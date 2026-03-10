/// Entry point for the THuntCloud ingester CLI.
///
/// Parses CLI arguments and dispatches to the appropriate ingestion command.
/// All output messages and log entries are written in English.
use std::path::PathBuf;
use std::process;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use duckdb::Connection;
use ingester::ingest::{IngestStats, ingest_with_progress};

/// THuntCloud ingester — ingest AWS CloudTrail logs into DuckDB.
#[derive(Debug, Parser)]
#[command(name = "ingester", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    /// Ingest CloudTrail log files into DuckDB.
    Ingest {
        /// Path to a file or directory containing CloudTrail log files.
        #[arg(short, long)]
        path: PathBuf,

        /// Path to the DuckDB database file.
        #[arg(short, long, default_value = "/data/threat_hunting.db")]
        db: PathBuf,

        /// Disable progress bar output.
        #[arg(long)]
        no_progress: bool,
    },
}

fn run() -> Result<IngestStats> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Ingest {
            path,
            db,
            no_progress,
        } => {
            let conn = Connection::open(&db)
                .with_context(|| format!("Failed to open DuckDB at {}", db.display()))?;
            ingest_with_progress(&path, &conn, !no_progress)
        }
    }
}

fn main() {
    match run() {
        Ok(stats) => {
            println!(
                "Ingestion complete: files_processed={} records_inserted={} errors={} elapsed_secs={:.2}",
                stats.files_processed, stats.records_inserted, stats.errors, stats.elapsed_secs,
            );
        }
        Err(e) => {
            eprintln!("error: {e:#}");
            process::exit(1);
        }
    }
}
