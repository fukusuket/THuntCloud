/// Entry point for the THuntCloud ingester CLI.
///
/// Parses CLI arguments and dispatches to the appropriate ingestion command.
/// All output messages and log entries are written in English.
use std::path::PathBuf;
use std::process;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use duckdb::Connection;
use ingester::date_filter::DateFilter;
use ingester::ingest::{IngestStats, ingest_with_filters};
use ingester::path_filter::PathFilter;

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

        /// Include only files whose path contains a date (yyyy/mm/dd) on or after
        /// this date. Format: YYYYMMDD (e.g. 20240115). CloudTrail stores logs under
        /// date-based directory segments; files with no date in their path are always included.
        #[arg(long, value_name = "YYYYMMDD")]
        from: Option<String>,

        /// Include only files whose path contains a date (yyyy/mm/dd) on or before
        /// this date. Format: YYYYMMDD (e.g. 20240131).
        #[arg(long, value_name = "YYYYMMDD")]
        to: Option<String>,

        /// Include only files whose full path matches at least one of these
        /// comma-separated glob patterns (e.g. `*CloudTrail*,*Config*`).
        /// `*` crosses path-separator boundaries.
        /// When omitted, all files are candidates.
        #[arg(long, value_name = "PATTERNS")]
        include: Option<String>,

        /// Exclude files whose full path matches any of these comma-separated
        /// glob patterns (e.g. `*vpcflowlogs*`).
        /// Evaluated after `--include`; a match here always wins.
        #[arg(long, value_name = "PATTERNS")]
        exclude: Option<String>,

        /// Number of worker threads used for parallel file parsing.
        /// Defaults to the number of logical CPU cores (rayon default).
        /// Set to 1 to disable parallelism, which minimises peak memory usage
        /// at the cost of throughput.
        #[arg(long, value_name = "N")]
        workers: Option<usize>,
    },
}

fn run() -> Result<IngestStats> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Ingest {
            path,
            db,
            no_progress,
            from,
            to,
            include,
            exclude,
            workers,
        } => {
            // Optionally cap the rayon thread pool before any parallel work.
            // --workers 1 disables parallelism (lowest memory, useful for
            // memory-constrained or single-core environments).
            if let Some(n) = workers {
                rayon::ThreadPoolBuilder::new()
                    .num_threads(n)
                    .build_global()
                    .ok(); // harmless if the pool is already initialised
            }

            // Build date filter (no-op when both from and to are None).
            let date_filter = DateFilter::from_strs(from.as_deref(), to.as_deref())
                .context("Invalid --from / --to argument")?;

            // Build path-pattern filter (no-op when both include and exclude are None).
            let path_filter = PathFilter::from_strs(include.as_deref(), exclude.as_deref())
                .context("Invalid --include / --exclude argument")?;

            // Resolve DB path: CLI arg > DUCKDB_PATH env > default
            let db_path = db.unwrap_or_else(|| {
                std::env::var("DUCKDB_PATH")
                    .map(PathBuf::from)
                    .unwrap_or_else(|_| PathBuf::from("/data/db/threat_hunting.db"))
            });
            let conn = Connection::open(&db_path)
                .with_context(|| format!("Failed to open DuckDB at {}", db_path.display()))?;
            ingest_with_filters(&path, &conn, !no_progress, &date_filter, &path_filter)
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
