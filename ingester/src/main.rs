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
        /// Falls back to the DUCKDB_PATH environment variable, then /data/db/threat_hunting.db.
        #[arg(short, long)]
        db: Option<PathBuf>,

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
            // Resolve DB path: CLI arg > DUCKDB_PATH env > default
            let db_path = db.unwrap_or_else(|| {
                std::env::var("DUCKDB_PATH")
                    .map(PathBuf::from)
                    .unwrap_or_else(|_| PathBuf::from("/data/db/threat_hunting.db"))
            });
            let conn = Connection::open(&db_path)
                .with_context(|| format!("Failed to open DuckDB at {}", db_path.display()))?;
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
