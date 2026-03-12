# Dashboard Module — Implementation Plan

> Based on PRD.md Section 6.3 and doc/ARCHITECTURE.md.
> All code comments, documentation, and commit messages MUST be written in English.
> This document is the source of truth for the dashboard module implementation schedule.

---

## Overview

The dashboard module provides a BI visualization layer for AWS CloudTrail logs stored in DuckDB. It is powered by **Apache Superset** running as a Docker container, pre-seeded with CloudTrail-specific charts and dashboards.

**DuckDB is always opened in `READ_ONLY` mode in this module.**

### Technology Stack

| Item | Value |
|------|-------|
| BI Tool | Apache Superset (latest) |
| DB Connector | `duckdb-engine` (SQLAlchemy dialect for DuckDB) |
| DB Access | DuckDB `READ_ONLY` |
| Base Image | `apache/superset:latest` |
| Dashboard Format | Superset export format (ZIP containing YAML) |
| Orchestration | Docker Compose |

### Relationship to Other Modules

```
ingester (Rust)          agent (Python/Streamlit)
   │ READ_WRITE               │ READ_ONLY
   ▼                          ▼
DuckDB ──────────────────────────────────────────▶ dashboard (Superset)
threat_hunting.db                                        │ READ_ONLY
                                                         ▼
                                              Pre-built CloudTrail charts
                                              + Ad-hoc SQL Lab (DSH-06)
```

### Key Technical Challenge: DuckDB + Superset Integration

The default `apache/superset:latest` image does **not** include `duckdb-engine`. A custom Docker image is required to install it. Additionally, Superset's DuckDB connection must be configured as READ_ONLY to comply with DuckDB's single-writer architecture.

### Implementation Overview — 5 Phases

| Phase | Goal | Estimated Time |
|-------|------|---------------|
| 0 | Custom Docker image with `duckdb-engine` | 0.5 h |
| 1 | Superset initialization (admin, DuckDB connection) | 1 h |
| 2 | Dataset definition (`cloudtrail_events`) | 1 h |
| 3 | Chart definitions (DSH-01 to DSH-05) | 2.5 h |
| 4 | Dashboard assembly, ZIP packaging, export (DSH-06/07) | 1.5 h |
| **Total** | | **~6.5 h** |

---

## Phase 0 — Custom Docker Image (Estimated: 0.5 h)

**Goal**: Build a custom Superset image with `duckdb-engine` pre-installed so that DuckDB appears as a connectable database in Superset.

### Why a Custom Image?

The official `apache/superset:latest` image does not bundle `duckdb-engine`. Attempting to add a DuckDB connection without it will fail with a `ModuleNotFoundError`. A one-line `pip install` in a custom `Dockerfile` resolves this.

### Deliverables

| File | Action |
|------|--------|
| `dashboard/Dockerfile` | Create — custom Superset image |
| `dashboard/superset_config.py` | Create — Superset configuration overrides |
| `docker/docker-compose.yml` | Modify — switch `superset` service to custom build |

### dashboard/Dockerfile

```dockerfile
# Custom Apache Superset image with DuckDB support.
# Installs duckdb-engine (SQLAlchemy dialect) and the duckdb Python package.
FROM apache/superset:latest

USER root

RUN pip install --no-cache-dir \
    duckdb>=1.2.0 \
    duckdb-engine>=0.13.0

USER superset
```

### dashboard/superset_config.py

```python
"""Superset configuration overrides for THuntCloud.

This file is mounted into the Superset container at
/app/pythonpath/superset_config.py and is loaded automatically by Superset.
"""

import os

# Secret key for session signing — MUST be overridden in production via env var.
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change-me-in-production")

# Disable the default example dashboards to keep the UI clean.
SUPERSET_LOAD_EXAMPLES = False

# Allow DuckDB as a valid database engine (additional engines can be listed here).
PREVENT_UNSAFE_DB_CONNECTIONS = True

# Feature flags
FEATURE_FLAGS = {
    # Enable the Alerts & Reports feature (optional)
    "ALERTS_ATTACH_REPORTS": False,
    # Enable dashboard-level CSS customization
    "DASHBOARD_NATIVE_FILTERS": True,
    # Enable drag-and-drop chart layout
    "ENABLE_EXPLORE_DRAG_AND_DROP": True,
}
```

### docker-compose.yml Changes

Modify the `superset` and `superset-init` services to use the custom build instead of `apache/superset:latest`:

```yaml
# Before (existing):
superset:
  image: apache/superset:latest

superset-init:
  image: apache/superset:latest

# After (change to):
superset:
  build:
    context: ../dashboard
    dockerfile: Dockerfile
  # (remove the image: line)

superset-init:
  build:
    context: ../dashboard
    dockerfile: Dockerfile
  # (remove the image: line)
```

Also add the `superset_config.py` mount to both services:

```yaml
volumes:
  - superset_home:/app/superset_home
  - ../dashboard/assets:/app/dashboards:ro
  - ../dashboard/superset_config.py:/app/pythonpath/superset_config.py:ro  # ADD
```

### Verification Checklist — Phase 0

- [ ] `docker compose build superset` completes without errors
- [ ] `docker compose run --rm superset python -c "import duckdb_engine; print('OK')"` prints `OK`
- [ ] Image size is reasonable (< 2 GB)

---

## Phase 1 — Superset Initialization (Estimated: 1 h)

**Goal**: On first `docker compose up`, automatically create the admin user, run DB migrations, and register the DuckDB connection — all without manual browser interaction.

### Deliverables

| File | Action |
|------|--------|
| `dashboard/init/bootstrap.sh` | Create — idempotent init script |
| `dashboard/init/datasource_duckdb.yaml` | Create — DuckDB connection definition |

### dashboard/init/bootstrap.sh

```bash
#!/usr/bin/env bash
# bootstrap.sh — Idempotent Superset initialization for THuntCloud.
# Runs inside the superset-init container on first startup.
set -e

echo "==> Running Superset DB migrations..."
superset db upgrade

echo "==> Creating admin user (idempotent)..."
superset fab create-admin \
  --username "${SUPERSET_ADMIN_USERNAME:-admin}" \
  --firstname "${SUPERSET_ADMIN_FIRSTNAME:-Admin}" \
  --lastname  "${SUPERSET_ADMIN_LASTNAME:-User}" \
  --email     "${SUPERSET_ADMIN_EMAIL:-admin@localhost}" \
  --password  "${SUPERSET_ADMIN_PASSWORD:-admin}" 2>/dev/null || true

echo "==> Initializing Superset roles and permissions..."
superset init

echo "==> Importing DuckDB database connection..."
superset set_database_uri \
  --database_name "CloudTrail DuckDB" \
  --uri "duckdb:////data/db/threat_hunting.db?read_only=true" 2>/dev/null || true

echo "==> Importing pre-built dashboard (if available)..."
if [ -f /app/dashboards/cloudtrail_default.zip ]; then
  superset import_dashboards -p /app/dashboards/cloudtrail_default.zip || true
else
  echo "    Dashboard ZIP not found — skipping import."
fi

echo "==> Bootstrap complete."
```

### docker-compose.yml: superset-init entrypoint update

```yaml
superset-init:
  build:
    context: ../dashboard
    dockerfile: Dockerfile
  container_name: threat-hunting-superset-init
  volumes:
    - superset_home:/app/superset_home
    - ../dashboard/assets:/app/dashboards:ro
    - ../dashboard/superset_config.py:/app/pythonpath/superset_config.py:ro
    - ../dashboard/init/bootstrap.sh:/app/bootstrap.sh:ro
  environment:
    - SUPERSET_SECRET_KEY=${SUPERSET_SECRET_KEY:-change-me-in-production}
    - SUPERSET_ADMIN_USERNAME=${SUPERSET_ADMIN_USERNAME:-admin}
    - SUPERSET_ADMIN_PASSWORD=${SUPERSET_ADMIN_PASSWORD:-admin}
    - SUPERSET_ADMIN_EMAIL=${SUPERSET_ADMIN_EMAIL:-admin@localhost}
  entrypoint: ["/bin/bash", "/app/bootstrap.sh"]
  restart: "no"
```

### DuckDB Connection String

| Parameter | Value |
|-----------|-------|
| URI | `duckdb:////data/db/threat_hunting.db?read_only=true` |
| Display Name | `CloudTrail DuckDB` |
| Engine | `duckdb` (provided by `duckdb-engine`) |
| Access Mode | READ_ONLY (enforced by `?read_only=true`) |

> **Note**: Four slashes (`////`) are required: `duckdb://` (scheme) + `//` (empty host) + `/data/db/...` (absolute path).

### Verification Checklist — Phase 1

- [ ] `docker compose up` completes; `superset-init` exits with code 0
- [ ] `http://localhost:8088` is accessible
- [ ] Login with `admin` / `admin` succeeds
- [ ] Settings → Database Connections shows `CloudTrail DuckDB`
- [ ] "Test Connection" on `CloudTrail DuckDB` passes

---

## Phase 2 — Dataset Definition (Estimated: 1 h)

**Goal**: Register the `cloudtrail_events` table as a Superset Dataset so it can be used by charts. Define calculated columns and a default time column.

### Deliverables

| File | Action |
|------|--------|
| `dashboard/assets/cloudtrail_default/metadata.yaml` | Create — dashboard metadata |
| `dashboard/assets/cloudtrail_default/databases/CloudTrail_DuckDB.yaml` | Create — DB reference |
| `dashboard/assets/cloudtrail_default/datasets/cloudtrail_events.yaml` | Create — dataset definition |

### dashboard/assets/cloudtrail_default/metadata.yaml

```yaml
# Superset dashboard export metadata
version: 1.0.0
type: Dashboard
timestamp: "2026-03-11T00:00:00+00:00"
```

### dashboard/assets/cloudtrail_default/databases/CloudTrail_DuckDB.yaml

```yaml
# Superset database connection definition for DuckDB.
database_name: CloudTrail DuckDB
sqlalchemy_uri: "duckdb:////data/db/threat_hunting.db?read_only=true"
cache_timeout: null
expose_in_sqllab: true
allow_run_async: true
allow_ctas: false
allow_cvas: false
allow_dml: false
allow_multi_schema_metadata_fetch: false
impersonate_user: false
extra:
  metadata_params: {}
  engine_params: {}
  schemas_allowed_for_file_upload: []
```

### dashboard/assets/cloudtrail_default/datasets/cloudtrail_events.yaml

```yaml
# Superset dataset definition for cloudtrail_events.
table_name: cloudtrail_events
main_dttm_col: event_time
description: AWS CloudTrail events ingested by THuntCloud ingester.
default_endpoint: null
offset: 0
cache_timeout: null
schema: null
sql: null
params: null
template_params: null
filter_select_enabled: true
fetch_values_predicate: null
extra: null

columns:
  - column_name: event_time
    verbose_name: Event Time
    is_dttm: true
    type: TIMESTAMP
    description: Timestamp of the API call

  - column_name: event_name
    verbose_name: Event Name
    is_dttm: false
    type: VARCHAR
    description: Name of the AWS API action

  - column_name: event_source
    verbose_name: Event Source
    is_dttm: false
    type: VARCHAR
    description: AWS service that processed the request

  - column_name: aws_region
    verbose_name: AWS Region
    is_dttm: false
    type: VARCHAR

  - column_name: source_ip_address
    verbose_name: Source IP Address
    is_dttm: false
    type: VARCHAR

  - column_name: user_identity_type
    verbose_name: Identity Type
    is_dttm: false
    type: VARCHAR

  - column_name: user_identity_arn
    verbose_name: Identity ARN
    is_dttm: false
    type: VARCHAR

  - column_name: user_identity_account_id
    verbose_name: Account ID
    is_dttm: false
    type: VARCHAR

  - column_name: error_code
    verbose_name: Error Code
    is_dttm: false
    type: VARCHAR

  - column_name: error_message
    verbose_name: Error Message
    is_dttm: false
    type: VARCHAR

  - column_name: read_only
    verbose_name: Read Only
    is_dttm: false
    type: BOOLEAN

  - column_name: event_type
    verbose_name: Event Type
    is_dttm: false
    type: VARCHAR

metrics:
  - metric_name: count
    verbose_name: COUNT(*)
    metric_type: count
    expression: COUNT(*)
    description: Total number of events

  - metric_name: error_count
    verbose_name: Error Count
    metric_type: count
    expression: "COUNT(CASE WHEN error_code IS NOT NULL THEN 1 END)"
    description: Number of events with an error code

  - metric_name: write_count
    verbose_name: Write Event Count
    metric_type: count
    expression: "COUNT(CASE WHEN read_only = false THEN 1 END)"
    description: Number of mutating (non-read-only) API calls
```

### Verification Checklist — Phase 2

- [ ] SQL Lab → `SELECT COUNT(*) FROM cloudtrail_events` returns a number (not an error)
- [ ] SQL Lab → `SELECT event_time, event_name FROM cloudtrail_events LIMIT 10` returns rows
- [ ] Datasets menu shows `cloudtrail_events` linked to `CloudTrail DuckDB`
- [ ] Dataset detail page shows `event_time` as the main datetime column

---

## Phase 3 — Chart Definitions (Estimated: 2.5 h)

**Goal**: Create 5 chart YAML definitions covering DSH-01 through DSH-05.

### Deliverables

| File | Requirement |
|------|-------------|
| `dashboards/cloudtrail_default/charts/event_timeseries.yaml` | DSH-01 |
| `dashboards/cloudtrail_default/charts/top_api_calls.yaml` | DSH-02 |
| `dashboards/cloudtrail_default/charts/iam_entity_activity.yaml` | DSH-03 |
| `dashboards/cloudtrail_default/charts/error_trend.yaml` | DSH-04 |
| `dashboards/cloudtrail_default/charts/source_ip_requests.yaml` | DSH-05 |

---

### DSH-01: CloudTrail Event Time-Series Chart

**Chart type**: `echarts_timeseries_bar` (Time-series Bar Chart)

**SQL**:
```sql
SELECT
    date_trunc('hour', event_time) AS hour,
    COUNT(*)                       AS event_count
FROM cloudtrail_events
GROUP BY 1
ORDER BY 1
```

**charts/event_timeseries.yaml**:
```yaml
slice_name: CloudTrail Events Over Time
viz_type: echarts_timeseries_bar
description: Hourly count of CloudTrail API calls over time (DSH-01).
query_context: null
params:
  x_axis: hour
  time_grain_sqla: PT1H
  metrics:
    - event_count
  adhoc_filters: []
  row_limit: 10000
  x_axis_title: Time
  y_axis_title: Event Count
  color_scheme: supersetColors
cache_timeout: null
```

---

### DSH-02: Top-N API Call Ranking

**Chart type**: `bar` (Horizontal Bar Chart)

**SQL**:
```sql
SELECT
    event_name,
    COUNT(*) AS call_count
FROM cloudtrail_events
GROUP BY event_name
ORDER BY call_count DESC
LIMIT 20
```

**charts/top_api_calls.yaml**:
```yaml
slice_name: Top 20 API Calls
viz_type: bar
description: The 20 most frequently called AWS API actions (DSH-02).
params:
  metrics:
    - call_count
  groupby:
    - event_name
  row_limit: 20
  order_desc: true
  orientation: horizontal
  x_axis_label: Call Count
  y_axis_label: API Action
  color_scheme: supersetColors
cache_timeout: null
```

---

### DSH-03: Activity Aggregation by IAM Entity

**Chart type**: `table` (Table with conditional formatting)

**SQL**:
```sql
SELECT
    COALESCE(user_identity_arn, 'Unknown')  AS iam_entity,
    user_identity_type                       AS identity_type,
    COUNT(*)                                 AS total_events,
    COUNT(CASE WHEN read_only = false THEN 1 END) AS write_events,
    COUNT(CASE WHEN error_code IS NOT NULL THEN 1 END) AS error_events
FROM cloudtrail_events
GROUP BY 1, 2
ORDER BY total_events DESC
LIMIT 50
```

**charts/iam_entity_activity.yaml**:
```yaml
slice_name: IAM Entity Activity
viz_type: table
description: Top 50 IAM entities ranked by total API calls, with write and error breakdowns (DSH-03).
params:
  metrics:
    - total_events
    - write_events
    - error_events
  groupby:
    - iam_entity
    - identity_type
  row_limit: 50
  order_desc: true
  table_timestamp_format: smart_date
  conditional_formatting:
    - col: write_events
      operator: ">"
      targetValue: 100
      colorScheme: red_white
  page_size: 25
cache_timeout: null
```

---

### DSH-04: Error Occurrence Trend

**Chart type**: `echarts_timeseries_bar` (Stacked Bar Chart)

**SQL**:
```sql
SELECT
    date_trunc('hour', event_time) AS hour,
    COALESCE(error_code, 'NoError') AS error_code,
    COUNT(*)                        AS error_count
FROM cloudtrail_events
WHERE error_code IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 3 DESC
```

**charts/error_trend.yaml**:
```yaml
slice_name: Error Occurrence Trend
viz_type: echarts_timeseries_bar
description: Hourly error counts grouped by error code — useful for detecting spikes in AccessDenied (DSH-04).
params:
  x_axis: hour
  time_grain_sqla: PT1H
  metrics:
    - error_count
  groupby:
    - error_code
  adhoc_filters:
    - clause: WHERE
      expressionType: SQL
      sqlExpression: "error_code IS NOT NULL"
  row_limit: 10000
  stack: true
  x_axis_title: Time
  y_axis_title: Error Count
  color_scheme: supersetColors
cache_timeout: null
```

---

### DSH-05: Source IP Request Count (Should)

**Chart type**: `table` (sortable, for IP drill-down)

> **Note on Geo-Map**: A world map visualization (DSH-05 original intent) requires IP-to-geolocation enrichment (e.g., MaxMind GeoLite2), which is outside the scope of v1.0. A sortable table of top source IPs is provided as an equivalent. Geo-map is deferred to v2.0.

**SQL**:
```sql
SELECT
    source_ip_address,
    COUNT(*)                                      AS request_count,
    COUNT(DISTINCT user_identity_arn)             AS unique_identities,
    COUNT(CASE WHEN read_only = false THEN 1 END) AS write_requests
FROM cloudtrail_events
WHERE source_ip_address IS NOT NULL
  AND source_ip_address NOT LIKE '%.amazonaws.com'
GROUP BY source_ip_address
ORDER BY request_count DESC
LIMIT 100
```

**charts/source_ip_requests.yaml**:
```yaml
slice_name: Top Source IP Addresses
viz_type: table
description: Top 100 external source IPs by request count (DSH-05; geo-map deferred to v2.0).
params:
  metrics:
    - request_count
    - unique_identities
    - write_requests
  groupby:
    - source_ip_address
  row_limit: 100
  order_desc: true
  page_size: 25
cache_timeout: null
```

### Verification Checklist — Phase 3

- [ ] Each chart SQL runs without error in SQL Lab
- [ ] DSH-01: Time-series bar chart renders data points (not empty)
- [ ] DSH-02: Horizontal bar chart shows ≥ 1 API call
- [ ] DSH-03: Table shows IAM entities with correct counts
- [ ] DSH-04: Stacked bar chart shows error breakdown (visible only if error events exist)
- [ ] DSH-05: Source IP table shows rows

---

## Phase 4 — Dashboard Assembly & Export (Estimated: 1.5 h)

**Goal**: Combine all 5 charts into a single "CloudTrail Threat Hunting" dashboard, package it as a ZIP for `superset import_dashboards`, and document DSH-06/DSH-07.

### Deliverables

| File | Action |
|------|--------|
| `dashboard/assets/cloudtrail_default/dashboard.yaml` | Create — dashboard layout definition |
| `dashboard/assets/cloudtrail_default.zip` | Create — packaged for `superset import_dashboards` |

### dashboard/assets/cloudtrail_default/dashboard.yaml

```yaml
dashboard_title: CloudTrail Threat Hunting
description: >
  Pre-built threat hunting dashboard for AWS CloudTrail logs.
  Covers event volume, top API calls, IAM activity, error trends, and source IPs.
  Use SQL Lab (DSH-06) for ad-hoc investigation queries.
published: true
css: ""
slug: cloudtrail-threat-hunting

# Layout: 2-column grid, charts stacked vertically
position_json: |
  {
    "DASHBOARD_VERSION_KEY": "v2",
    "ROOT_ID": {
      "type": "ROOT",
      "id": "ROOT_ID",
      "children": ["GRID_ID"]
    },
    "GRID_ID": {
      "type": "GRID",
      "id": "GRID_ID",
      "children": ["ROW-1", "ROW-2", "ROW-3"]
    },
    "ROW-1": {
      "type": "ROW",
      "id": "ROW-1",
      "children": ["CHART-timeseries"],
      "meta": {"background": "BACKGROUND_TRANSPARENT"}
    },
    "ROW-2": {
      "type": "ROW",
      "id": "ROW-2",
      "children": ["CHART-top-api", "CHART-iam-entity"],
      "meta": {"background": "BACKGROUND_TRANSPARENT"}
    },
    "ROW-3": {
      "type": "ROW",
      "id": "ROW-3",
      "children": ["CHART-error-trend", "CHART-source-ip"],
      "meta": {"background": "BACKGROUND_TRANSPARENT"}
    },
    "CHART-timeseries": {
      "type": "CHART",
      "id": "CHART-timeseries",
      "meta": {"chartId": 1, "width": 12, "height": 50, "sliceName": "CloudTrail Events Over Time"}
    },
    "CHART-top-api": {
      "type": "CHART",
      "id": "CHART-top-api",
      "meta": {"chartId": 2, "width": 6, "height": 50, "sliceName": "Top 20 API Calls"}
    },
    "CHART-iam-entity": {
      "type": "CHART",
      "id": "CHART-iam-entity",
      "meta": {"chartId": 3, "width": 6, "height": 50, "sliceName": "IAM Entity Activity"}
    },
    "CHART-error-trend": {
      "type": "CHART",
      "id": "CHART-error-trend",
      "meta": {"chartId": 4, "width": 6, "height": 50, "sliceName": "Error Occurrence Trend"}
    },
    "CHART-source-ip": {
      "type": "CHART",
      "id": "CHART-source-ip",
      "meta": {"chartId": 5, "width": 6, "height": 50, "sliceName": "Top Source IP Addresses"}
    }
  }

metadata:
  charts:
    - slice_name: CloudTrail Events Over Time
      viz_type: echarts_timeseries_bar
    - slice_name: Top 20 API Calls
      viz_type: bar
    - slice_name: IAM Entity Activity
      viz_type: table
    - slice_name: Error Occurrence Trend
      viz_type: echarts_timeseries_bar
    - slice_name: Top Source IP Addresses
      viz_type: table
```

### ZIP Packaging Script

Run from the repository root to produce `dashboard/assets/cloudtrail_default.zip`:

```bash
cd dashboard/assets
python3 rebuild_zip.py
```

The ZIP structure must be:
```
cloudtrail_default.zip
└── cloudtrail_default/
    ├── metadata.yaml
    ├── dashboard.yaml
    ├── databases/
    │   └── CloudTrail_DuckDB.yaml
    ├── datasets/
    │   └── cloudtrail_events.yaml
    └── charts/
        ├── event_timeseries.yaml
        ├── top_api_calls.yaml
        ├── iam_entity_activity.yaml
        ├── error_trend.yaml
        └── source_ip_requests.yaml
```

---

### DSH-06: Ad-hoc SQL Visualization (Must)

**No custom chart definition is required.** Superset's built-in **SQL Lab** (accessible from the top navigation bar) covers this requirement out of the box.

Users can:
1. Navigate to **SQL Lab → SQL Editor**
2. Select `CloudTrail DuckDB` as the database
3. Write and execute arbitrary DuckDB-compatible SQL
4. Click **Explore** to visualize results as any chart type
5. Save the chart and add it to any dashboard

> The `expose_in_sqllab: true` flag set in `databases/CloudTrail_DuckDB.yaml` (Phase 2) enables this.

---

### DSH-07: Dashboard Export (Should)

**No custom implementation is required.** Superset provides two built-in export paths:

| Method | How to use |
|--------|-----------|
| Download as image (PNG) | Dashboard menu → **Download** → **Download as image** |
| Export to PDF | Dashboard menu → **Download** → **Export to PDF** |
| Export dashboard definition | Dashboard menu → **Export** (produces a ZIP for re-import) |

> Ensure `FEATURE_FLAGS["DASHBOARD_NATIVE_FILTERS"] = True` is set in `superset_config.py` (already included in Phase 0) to enable the full export menu.

### Verification Checklist — Phase 4

- [ ] `dashboard/assets/cloudtrail_default.zip` exists and can be unzipped without errors
- [ ] `superset import_dashboards -p /app/dashboards/cloudtrail_default.zip` exits 0
- [ ] "CloudTrail Threat Hunting" dashboard appears in Superset after import
- [ ] All 5 charts are visible on the dashboard canvas
- [ ] DSH-06: SQL Lab is accessible and `SELECT 1` executes against `CloudTrail DuckDB`
- [ ] DSH-07: Dashboard download menu shows image and PDF options

---

## Final Module Structure

```
dashboard/
├── Dockerfile                              # Custom Superset image (duckdb-engine)
├── superset_config.py                      # Superset configuration overrides
├── assets/                                 # Pre-built dashboard definitions and ZIP exports
│   ├── cloudtrail_default/                 # Dashboard source files
│   │   ├── metadata.yaml
│   │   ├── dashboard.yaml
│   │   ├── databases/
│   │   │   └── CloudTrail_DuckDB.yaml
│   │   ├── datasets/
│   │   │   └── cloudtrail_events.yaml
│   │   └── charts/
│   │       ├── event_timeseries.yaml           # DSH-01
│   │       ├── top_api_calls.yaml              # DSH-02
│   │       ├── iam_entity_activity.yaml        # DSH-03
│   │       ├── error_trend.yaml                # DSH-04
│   │       └── source_ip_requests.yaml         # DSH-05
│   ├── cloudtrail_default.zip              # Packaged for superset import_dashboards
│   └── rebuild_zip.py                      # Helper to regenerate the ZIP
└── init/
    └── bootstrap.sh                        # Idempotent init script
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPERSET_SECRET_KEY` | `change-me-in-production` | **Must be changed** — used for session signing |
| `DUCKDB_PATH` | `/data/db/threat_hunting.db` | Path to DuckDB file inside the container |
| `SUPERSET_ADMIN_USERNAME` | `admin` | Admin username created by bootstrap.sh |
| `SUPERSET_ADMIN_PASSWORD` | `admin` | **Must be changed** in production |
| `SUPERSET_ADMIN_EMAIL` | `admin@localhost` | Admin email |

> **Security**: Set `SUPERSET_SECRET_KEY` and `SUPERSET_ADMIN_PASSWORD` via `.env` file (never commit to git).

---

## docker-compose.yml: Full Diff Summary

| Section | Change |
|---------|--------|
| `superset.image` | Remove — replaced by `build:` |
| `superset.build` | Add `context: ../dashboard, dockerfile: Dockerfile` |
| `superset.volumes` | Add mount for `superset_config.py` |
| `superset-init.image` | Remove — replaced by `build:` |
| `superset-init.build` | Add `context: ../dashboard, dockerfile: Dockerfile` |
| `superset-init.volumes` | Add mounts for `superset_config.py` and `bootstrap.sh` |
| `superset-init.entrypoint` | Change to `["/bin/bash", "/app/bootstrap.sh"]` |
| `superset-init.environment` | Add `SUPERSET_ADMIN_*` variables |

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `duckdb-engine` version incompatibility with Superset's SQLAlchemy | High | Pin versions in `Dockerfile`; test with `python -c "import duckdb_engine"` in CI |
| Superset image update breaks custom `Dockerfile` | Medium | Pin `apache/superset:X.Y.Z` (use a specific version tag, not `latest`) in production |
| `cloudtrail_default.zip` format mismatch across Superset versions | High | Always regenerate ZIP with `superset export_dashboards` after any Superset upgrade |
| DuckDB file locked by ingester during Superset query | Low | Standard workflow: ingester runs first, then Superset; READ_ONLY allows concurrent reads |
| `bootstrap.sh` re-running on container restart creates duplicate admin | Low | All `superset fab create-admin` calls include `|| true`; Superset prevents duplicates |
| DSH-05 geo-map requires external IP database (MaxMind) | Medium | Table view provided as v1.0 alternative; geo-map deferred to v2.0 |
| Large DuckDB files slow down Superset chart rendering | Medium | Apply `LIMIT` clauses in chart SQL; use `cache_timeout` per chart |

---

## Commit Convention Examples

```
feat(dashboard): add custom Dockerfile with duckdb-engine (Phase 0)
feat(dashboard): add bootstrap.sh for idempotent Superset init (Phase 1)
feat(dashboard): add cloudtrail_events dataset definition (Phase 2)
feat(dashboard): add event time-series chart DSH-01 (Phase 3)
feat(dashboard): add top API calls chart DSH-02 (Phase 3)
feat(dashboard): add IAM entity activity chart DSH-03 (Phase 3)
feat(dashboard): add error trend chart DSH-04 (Phase 3)
feat(dashboard): add source IP table chart DSH-05 (Phase 3)
feat(dashboard): assemble CloudTrail dashboard and package ZIP (Phase 4)
fix(dashboard): pin duckdb-engine version in Dockerfile
docs(dashboard): update DASHBOARD_IMPLEMENTATION_PLAN.md with Phase 0 completion
```

---

*This document is generated from PRD.md §6.3 and doc/ARCHITECTURE.md. Update it as each phase is completed.*

