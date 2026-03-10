# Architecture

## Language Policy

All architectural documentation, comments, and code annotations in this project MUST be written in English.

## System Overview

THuntCloud is a locally-executed, AI-assisted threat hunting tool for AWS CloudTrail logs. It consists of three independent containers orchestrated by Docker Compose, sharing a DuckDB database via a Docker Named Volume.

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐  ┌─────────────┐  │
│  │   ingester   │   │    agent     │  │  dashboard  │  │
│  │  (Rust)      │   │  (Streamlit) │  │  (Superset) │  │
│  │              │   │              │  │             │  │
│  │ CloudTrail   │   │  AI-Agent    │  │ BI / Viz    │  │
│  │ gz ingest    │   │ SQL gen/exec │  │             │  │
│  │ READ_WRITE   │   │ READ_ONLY    │  │ READ_ONLY   │  │
│  └──────┬───────┘   └──────┬───────┘  └──────┬──────┘  │
│         └──────────────────┴──────────────────┘         │
│                            │                            │
│                    ┌───────▼──────┐                     │
│                    │   DuckDB     │                     │
│                    │  Named Vol   │                     │
│                    │  (SSD)       │                     │
│                    └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### ingester (Rust)

**Purpose:** Parse AWS CloudTrail JSON/gz log files from the local filesystem and store them in DuckDB.

- Sole writer to DuckDB (`READ_WRITE` mode)
- Runs as a one-shot CLI command (Docker Compose profile: `ingest`)
- Handles gz decompression, JSON parsing, schema creation, and batch insertion
- Targets: 10 GB in under 5 minutes, 50 GB on 16 GB RAM

### agent (Python / Streamlit)

**Purpose:** AI-assisted interactive threat hunting UI.

- Reads from DuckDB (`READ_ONLY` mode)
- Generates SQL from natural language via OpenAI API
- Executes queries and displays results
- Generates threat hunting reports (Markdown / PDF)

### dashboard (Apache Superset)

**Purpose:** BI dashboard for log visualization.

- Reads from DuckDB (`READ_ONLY` mode)
- Pre-seeded with CloudTrail-specific dashboards
- Supports ad-hoc SQL visualization

## DuckDB Sharing Strategy

### Decision: Docker Named Volume + 1-Writer / N-Readers

DuckDB is an in-process database. It does not support concurrent writes from multiple processes. However, multiple `READ_ONLY` connections are permitted while one process holds the write lock.

```
┌─────────────────────────────────────────────────────────────┐
│           Docker Named Volume: duckdb_data                  │
│           Mounted on host NVMe/SSD (recommended)            │
└────────────┬────────────────────┬───────────────────────────┘
             │ READ_WRITE (1)     │ READ_ONLY (multiple)
             ▼                    ▼
        ingester             agent / dashboard
      (write only)           (read only)
```

### Access Rules

1. `ingester` opens the database as `READ_WRITE` — it is the exclusive writer.
2. `agent` and `dashboard` open the database as `READ_ONLY` — they are concurrent readers.
3. The default workflow is sequential: ingester completes ingestion first, then agent/dashboard query.
4. SSD storage (SATA or NVMe) is strongly recommended; HDD is discouraged.

### Alternatives Considered

| Option                         | Performance | Concurrency    | Complexity | Decision     |
| ------------------------------ | ----------- | -------------- | ---------- | ------------ |
| **Named Volume + READ_ONLY**   | ◎           | 1W / nR        | Low        | **Adopted**  |
| Bind Mount (host path)         | ◎           | 1W / nR        | Low        | Equivalent   |
| DuckLake extension             | ○           | Multiple W     | High       | v2+ consider |
| Arrow Flight proxy             | △           | Multiple W     | High       | Rejected     |
| NAS / network storage          | ✕           | ✕              | Low        | Rejected     |

## Data Flow

```
CloudTrail logs (.json / .json.gz)
        │
        ▼
┌───────────────┐
│  ingester     │
│               │
│  1. Walk dir  │
│  2. Detect gz │──→ flate2 decompression
│  3. Parse JSON│──→ serde_json deserialization
│  4. Insert DB │──→ DuckDB batch appender
│  5. Track     │──→ Duplicate prevention (checksum)
└───────┬───────┘
        │ DuckDB READ_WRITE
        ▼
┌───────────────┐
│  DuckDB       │
│  threat_      │
│  hunting.db   │
└───────┬───────┘
        │ DuckDB READ_ONLY
        ▼
┌───────────────┐     ┌────────────────┐
│  agent        │     │  dashboard     │
│               │     │                │
│  User query   │     │ Pre-built      │
│  → AI → SQL   │     │ charts/tables  │
│  → Execute    │     │                │
│  → Analyze    │     │                │
│  → Report     │     │                │
└───────────────┘     └────────────────┘
```

## CloudTrail Table Schema

The ingester creates and populates the following table:

```sql
CREATE TABLE IF NOT EXISTS cloudtrail_events (
    event_time           TIMESTAMP,
    event_name           VARCHAR,
    event_source         VARCHAR,
    aws_region           VARCHAR,
    source_ip_address    VARCHAR,
    user_agent           VARCHAR,
    user_identity_type   VARCHAR,
    user_identity_arn    VARCHAR,
    user_identity_account_id VARCHAR,
    request_parameters   JSON,
    response_elements    JSON,
    error_code           VARCHAR,
    error_message        VARCHAR,
    read_only            BOOLEAN,
    event_type           VARCHAR,
    recipient_account_id VARCHAR,
    raw_event            JSON
);
```

### Schema Design Decisions

| Decision                           | Rationale                                                                |
| ---------------------------------- | ------------------------------------------------------------------------ |
| Flatten `userIdentity` fields      | Most queries filter/group by identity type, ARN, or account ID           |
| Keep `request/response` as JSON    | Too varied to normalize; DuckDB's JSON functions provide flexible access |
| Store `raw_event` as JSON          | Preserves the original record for auditing and ad-hoc deep inspection    |
| Use `TIMESTAMP` for `event_time`   | Enables native time-range queries and DuckDB temporal functions          |
| No primary key in v1.0             | DuckDB does not enforce PK constraints; duplicate prevention is external |

## Docker Compose Services

| Service          | Port  | Volume Access | Description                                 |
| ---------------- | ----- | ------------- | ------------------------------------------- |
| `ingester`       | —     | READ_WRITE    | CLI log ingestion (profile: `ingest`)       |
| `agent`          | 8501  | READ_ONLY     | Streamlit AI hunting UI                     |
| `superset`       | 8088  | READ_ONLY     | Apache Superset BI dashboard                |
| `superset-init`  | —     | —             | One-shot Superset initialization            |

### Volumes

| Volume              | Purpose                                      |
| ------------------- | -------------------------------------------- |
| `duckdb_data`       | Shared DuckDB database file                  |
| `superset_home`     | Superset metadata and configuration          |

## Security Architecture

```
┌──────────────────────────────────────────────────┐
│                  Local Machine                    │
│                                                   │
│  ┌──────────────┐    ┌─────────────────────────┐ │
│  │  .env file   │───▶│  OPENAI_API_KEY         │ │
│  │  (git-       │    │  SUPERSET_SECRET_KEY    │ │
│  │   ignored)   │    └─────────────────────────┘ │
│  └──────────────┘                                 │
│                                                   │
│  ┌──────────────┐    ┌─────────────────────────┐ │
│  │  agent       │───▶│  OpenAI API (external)  │ │
│  │  READ_ONLY   │    │  Only SQL gen requests  │ │
│  │  + EXPLAIN   │    └─────────────────────────┘ │
│  │  + keyword   │                                 │
│  │    filter     │    No other external calls     │
│  └──────────────┘                                 │
│                                                   │
│  DuckDB data never leaves the local machine       │
└──────────────────────────────────────────────────┘
```

## Future Extension Points (v2.0)

### Plugin Architecture for Log Sources

```rust
// v2.0 conceptual design
pub trait LogIngester: Send + Sync {
    fn source_id(&self) -> &str;
    fn ingest(&self, input: &IngesterInput, db: &DuckDBHandle) -> Result<IngestStats>;
    fn supported_patterns(&self) -> Vec<&str>;
}
```

### Planned Plugins

| Plugin          | Target Log        | Version |
| --------------- | ----------------- | ------- |
| `cloudtrail`    | CloudTrail JSON/gz | v1.0   |
| `vpc_flowlogs`  | VPC Flow Logs      | v2.0   |
| `s3_access`     | S3 Access Logs     | v2.0   |
| `waf`           | AWS WAF Logs       | v2.0   |
| `guardduty`     | GuardDuty Findings | v2.0   |

