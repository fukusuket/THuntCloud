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
use ingester::enrich::enrich_existing;
use ingester::geoip::{GeoipConfig, GeoipEnricher};
use ingester::ingest::{ingest_with_filters, ingest_with_geoip};
use ingester::path_filter::PathFilter;

/// Read an environment variable, returning `None` for both unset and empty values.
///
/// Docker Compose sets `VAR=${VAR:-}` which produces an empty string when the
/// host variable is unset. We treat `""` the same as absent.
fn env_var_non_empty(key: &str) -> Option<PathBuf> {
    std::env::var(key)
        .ok()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
}

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

        /// Path to GeoLite2-City.mmdb for geo-enrichment of source_ip_address.
        /// Falls back to the GEOIP_CITY_PATH environment variable.
        /// When omitted, geo columns are stored as NULL (unless --geoip-country is set).
        #[arg(long, value_name = "PATH")]
        geoip_city: Option<PathBuf>,

        /// Path to GeoLite2-Country.mmdb (lighter alternative to --geoip-city).
        /// Falls back to the GEOIP_COUNTRY_PATH environment variable.
        /// Provides country_code and country_name only; city/lat/lon will be NULL.
        /// Ignored when --geoip-city is also set.
        #[arg(long, value_name = "PATH")]
        geoip_country: Option<PathBuf>,

        /// Path to GeoLite2-ASN.mmdb for ASN/org enrichment.
        /// Falls back to the GEOIP_ASN_PATH environment variable.
        /// Works with both --geoip-city and --geoip-country.
        #[arg(long, value_name = "PATH")]
        geoip_asn: Option<PathBuf>,
    },

    /// Enrich existing cloudtrail_events rows with GeoIP data.
    ///
    /// Back-fills geo columns for a database that was ingested without a
    /// GeoIP enricher.  Only rows where geo_country_code IS NULL are updated.
    Enrich {
        /// Path to the DuckDB database file.
        /// Falls back to the DUCKDB_PATH environment variable, then /data/db/threat_hunting.db.
        #[arg(short, long)]
        db: Option<PathBuf>,

        /// Path to GeoLite2-City.mmdb.
        /// Falls back to the GEOIP_CITY_PATH environment variable.
        #[arg(long, value_name = "PATH")]
        geoip_city: Option<PathBuf>,

        /// Path to GeoLite2-Country.mmdb (lighter alternative to --geoip-city).
        /// Falls back to the GEOIP_COUNTRY_PATH environment variable.
        /// Provides country_code and country_name only; city/lat/lon will be NULL.
        /// Ignored when --geoip-city is also set.
        #[arg(long, value_name = "PATH")]
        geoip_country: Option<PathBuf>,

        /// Path to GeoLite2-ASN.mmdb.
        /// Falls back to the GEOIP_ASN_PATH environment variable.
        #[arg(long, value_name = "PATH")]
        geoip_asn: Option<PathBuf>,
    },
}

fn run() -> Result<()> {
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
            geoip_city,
            geoip_country,
            geoip_asn,
        } => {
            // Optionally cap the rayon thread pool before any parallel work.
            if let Some(n) = workers {
                rayon::ThreadPoolBuilder::new()
                    .num_threads(n)
                    .build_global()
                    .ok();
            }

            let date_filter = DateFilter::from_strs(from.as_deref(), to.as_deref())
                .context("Invalid --from / --to argument")?;
            let path_filter = PathFilter::from_strs(include.as_deref(), exclude.as_deref())
                .context("Invalid --include / --exclude argument")?;

            let db_path = db.unwrap_or_else(|| {
                std::env::var("DUCKDB_PATH")
                    .map(PathBuf::from)
                    .unwrap_or_else(|_| PathBuf::from("/data/db/threat_hunting.db"))
            });
            let conn = Connection::open(&db_path)
                .with_context(|| format!("Failed to open DuckDB at {}", db_path.display()))?;

            // Resolve GeoIP paths: CLI arg > env var (non-empty) > None.
            let city_path = geoip_city.or_else(|| env_var_non_empty("GEOIP_CITY_PATH"));
            let country_path = geoip_country.or_else(|| env_var_non_empty("GEOIP_COUNTRY_PATH"));
            let asn_path = geoip_asn.or_else(|| env_var_non_empty("GEOIP_ASN_PATH"));

            let stats = if city_path.is_some() || country_path.is_some() {
                let enricher = GeoipEnricher::open(&GeoipConfig {
                    city_db_path: city_path,
                    country_db_path: country_path,
                    asn_db_path: asn_path,
                })
                .context("Failed to open GeoIP database")?;
                ingest_with_geoip(
                    &path,
                    &conn,
                    !no_progress,
                    &date_filter,
                    &path_filter,
                    &enricher,
                )?
            } else {
                ingest_with_filters(&path, &conn, !no_progress, &date_filter, &path_filter)?
            };

            println!(
                "Ingestion complete: files_processed={} records_inserted={} errors={} elapsed_secs={:.2}",
                stats.files_processed, stats.records_inserted, stats.errors, stats.elapsed_secs,
            );
            Ok(())
        }

        Commands::Enrich {
            db,
            geoip_city,
            geoip_country,
            geoip_asn,
        } => {
            let db_path = db.unwrap_or_else(|| {
                std::env::var("DUCKDB_PATH")
                    .map(PathBuf::from)
                    .unwrap_or_else(|_| PathBuf::from("/data/db/threat_hunting.db"))
            });
            let conn = Connection::open(&db_path)
                .with_context(|| format!("Failed to open DuckDB at {}", db_path.display()))?;

            // Resolve GeoIP paths: CLI arg > env var (non-empty) > None.
            let city_path = geoip_city.or_else(|| env_var_non_empty("GEOIP_CITY_PATH"));
            let country_path = geoip_country.or_else(|| env_var_non_empty("GEOIP_COUNTRY_PATH"));
            let asn_path = geoip_asn.or_else(|| env_var_non_empty("GEOIP_ASN_PATH"));

            if city_path.is_none() && country_path.is_none() {
                anyhow::bail!(
                    "GeoLite2 database required: use --geoip-city, --geoip-country, \
                     or set GEOIP_CITY_PATH / GEOIP_COUNTRY_PATH"
                );
            }

            let enricher = GeoipEnricher::open(&GeoipConfig {
                city_db_path: city_path,
                country_db_path: country_path,
                asn_db_path: asn_path,
            })
            .context("Failed to open GeoIP database")?;

            let stats = enrich_existing(&conn, &enricher).context("Failed to enrich database")?;

            println!(
                "Enrichment complete: enriched_count={} skipped_count={} elapsed_secs={:.2}",
                stats.enriched_count, stats.skipped_count, stats.elapsed_secs,
            );
            Ok(())
        }
    }
}

fn main() {
    match run() {
        Ok(()) => {}
        Err(e) => {
            eprintln!("error: {e:#}");
            process::exit(1);
        }
    }
}
