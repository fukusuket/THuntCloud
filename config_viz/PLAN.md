# config_viz — Implementation Plan

> **Status: Phase C (Docker) — ✅ Complete.**

---

## Completed Work

### Rust ingester: `config-import` subcommand ✅

| File | Status |
|---|---|
| `ingester/src/config_parser.rs` | ✅ Done — CloudTrail JSON → typed structs |
| `ingester/src/config_db.rs` | ✅ Done — DuckDB schema + Appender writes |
| `ingester/src/config_import.rs` | ✅ Done — walk → SHA dedup → parse → insert pipeline |
| `ingester/src/main.rs` | ✅ Done — `config-import` subcommand wired |
| `ingester/tests/config_import_test.rs` | ✅ Done — CLI integration tests (CLI-CI-01, 02) |
| `ingester/tests/testdata_config/config_snapshot_mini.json` | ✅ Done — 2-resource test fixture |

CLI usage:

```bash
ingester config-import --path <dir>
                       [--db <path>]
                       [--no-progress]
```

DuckDB tables written: `config_snapshots`, `config_resources`, `config_edges`.

---

## Architecture Reference

### Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.12) + DuckDB READ_ONLY |
| Frontend | React 18 + Vite + TypeScript |
| Graph rendering | React Flow v11 (`reactflow`) |
| Auto layout | `dagre` |
| Styling | Tailwind CSS |
| Server state | TanStack Query v5 |
| Docker | Multi-stage build (Node build → Python runtime) |

### Directory Layout

```
config_viz/
├── PLAN.md
├── Dockerfile
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI app + static file serving
│   ├── db.py            # DuckDB READ_ONLY connection (lru_cache)
│   ├── query.py         # SQL queries (keyword blocklist + EXPLAIN)
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts   # outDir: ../static
│   ├── vitest.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── index.css
│       ├── App.tsx
│       ├── types.ts
│       ├── api.ts
│       ├── components/
│       │   ├── AwsNode.tsx
│       │   ├── GraphCanvas.tsx
│       │   ├── Sidebar.tsx
│       │   └── DetailPanel.tsx
│       └── utils/
│           ├── layout.ts
│           └── icons.ts
└── tests/
    ├── conftest.py      # tmp_duckdb fixture seeded with mini snapshot data
    └── test_query.py    # BA-01 〜 BA-10
```

### API Design

| Method | Path | Description |
|---|---|---|
| GET | `/api/snapshots` | List all ingested snapshots |
| GET | `/api/snapshots/{id}/resource-types` | Resource type list for a snapshot |
| GET | `/api/snapshots/{id}/graph` | Nodes + edges in React Flow format |
| GET | `/api/snapshots/{id}/resources/{rid}` | Single resource detail (configuration + tags) |
| GET | `/icons/{name}.png` | AWS icon static files |
| GET | `/` | React frontend (static) |

Query params: `resource_type=`, `limit=` (default 5000)

### DuckDB Tables (written by `ingester config-import`)

```sql
CREATE TABLE IF NOT EXISTS config_snapshots (
    snapshot_id  VARCHAR PRIMARY KEY,
    account_id   VARCHAR,
    aws_region   VARCHAR,
    captured_at  TIMESTAMP,
    source_path  VARCHAR,
    record_count INTEGER
);

CREATE TABLE IF NOT EXISTS config_resources (
    resource_id   VARCHAR,
    snapshot_id   VARCHAR,
    resource_type VARCHAR,
    aws_region    VARCHAR,
    resource_name VARCHAR,
    configuration VARCHAR,  -- JSON as VARCHAR
    tags          VARCHAR,  -- JSON as VARCHAR
    PRIMARY KEY (resource_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS config_edges (
    snapshot_id VARCHAR,
    source_id   VARCHAR,
    target_id   VARCHAR,
    edge_type   VARCHAR,
    PRIMARY KEY (snapshot_id, source_id, target_id, edge_type)
);
```

### Docker Compose Addition

```yaml
config-viz:
  build:
    context: ../config_viz
    dockerfile: Dockerfile
  container_name: threat-hunting-config-viz
  ports:
    - "8502:8502"
  volumes:
    - ${DUCKDB_HOST_PATH:-./data/db}:/data/db:ro
  environment:
    - DUCKDB_PATH=/data/db/threat_hunting.db
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8502/api/snapshots"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### Known Design Issues

1. **Dangling edges**: `relationships.resourceId` may reference resources outside the snapshot.
   → API filters edges to those where both endpoints exist in `config_resources` for the snapshot.

2. **Edge direction**: `relationships` records "self → target", but labels like "Is attached to"
   may feel more natural in reverse. → Normalise direction by `edge_type` in the API layer.

3. **AWS icons**: Require internet access at Docker build time.
   → Build failure must not break the app; placeholder fallback required.

---

## Phase A: FastAPI Backend (TDD with pytest)

**Status: ✅ Complete — 34/34 tests passing**

### Test List

| ID | Test | Target |
|---|---|---|
| BA-01 | Empty DB → `GET /api/snapshots` returns `[]` | `GET /api/snapshots` |
| BA-02 | 1 ingested row → `/api/snapshots` returns 1 item | `GET /api/snapshots` |
| BA-03 | `/api/snapshots/{id}/resource-types` returns correct type list | `GET /api/snapshots/{id}/resource-types` |
| BA-04 | `/api/snapshots/{id}/graph` node count matches resource count | `GET /api/snapshots/{id}/graph` |
| BA-05 | `/api/snapshots/{id}/graph` edges exclude dangling (both endpoints must exist) | same |
| BA-06 | `/api/snapshots/{id}/resources/{rid}` returns configuration + tags | `GET /api/snapshots/{id}/resources/{rid}` |
| BA-07 | Non-existent `snapshot_id` returns 404 | all endpoints |
| BA-08 | `resource_type=` query param filters graph nodes | graph endpoint |
| BA-09 | `limit=` query param caps node count | graph endpoint |
| BA-10 | READ_ONLY connection rejects write SQL (blocklist) | `query.py` |
| BA-11 | Graph nodes include `parentId` for containment hierarchy (VPC / Subnet / EC2) | graph endpoint |
| BA-11 | Container nodes use `type="awsGroupNode"`, leaves use `type="awsNode"` | graph endpoint |
| BA-11 | `is_container` field is True for nodes that contain other resources | graph endpoint |
| BA-11 | "Contains" edges excluded from edge list (expressed via parentId) | graph endpoint |
| BA-11 | `parentId` is None when parent is outside the filtered node set | graph endpoint |
| BA-12 | DB without Config tables → `/api/snapshots` returns `[]` gracefully | `GET /api/snapshots` |
| BA-12 | DB without Config tables → snapshot-scoped endpoints return 404 | all snapshot-scoped endpoints |
| BA-13 | Service group node present in full graph | graph endpoint |
| BA-13 | Physical resources have service group as parent | graph endpoint |
| BA-13 | Service group absent in filtered (`resource_type=`) view | graph endpoint |
| BA-14 | "Contains Subnet" edge sets `parentId` for containment | graph endpoint |
| BA-14 | Service group node is top-level for VPC | graph endpoint |
| BA-14 | Hierarchy depth is correct (region → service → VPC → subnet → instance) | graph endpoint |

### Red-Green-Refactor Order

1. BA-01 → create minimal FastAPI app skeleton + `GET /api/snapshots`
2. BA-02 → implement `db.py` READ_ONLY connection + snapshot list query
3. BA-03 → resource-types endpoint
4. BA-04 → graph endpoint (nodes only, no edges)
5. BA-05 → add edge filtering (dangling exclusion)
6. BA-06 → resource detail endpoint
7. BA-07 → 404 error handling
8. BA-08 → `resource_type=` filter
9. BA-09 → `limit=` cap
10. BA-10 → `query.py` keyword blocklist

### Completed (Phase A)

| File | Status |
|---|---|
| `config_viz/backend/__init__.py` | ✅ Done |
| `config_viz/backend/db.py` | ✅ Done — READ_ONLY DuckDB connection (get_conn dependency) |
| `config_viz/backend/query.py` | ✅ Done — list_snapshots, get_resource_types, get_graph, get_resource_detail, validate_sql |
| `config_viz/backend/main.py` | ✅ Done — FastAPI app with 4 API endpoints |
| `config_viz/backend/requirements.txt` | ✅ Done |
| `config_viz/requirements-dev.txt` | ✅ Done |
| `config_viz/pytest.ini` | ✅ Done |
| `config_viz/tests/conftest.py` | ✅ Done — tmp_db_empty, tmp_db_seeded, tmp_db_hierarchy, client_* fixtures |
| `config_viz/tests/test_query.py` | ✅ Done — 34 tests (BA-01 to BA-14) all passing |

---

## Phase B: React Frontend (TDD with Vitest + @testing-library/react)

**Status: ✅ Complete — 33/33 tests passing**

### Requirements (updated)

- **Hierarchical layout**: Region / VPC / Subnet shown as nested container boxes
  (like standard AWS architecture diagrams).
  - `awsGroupNode` — labeled rectangle with dashed border + AWS service icon.
  - `awsNode` — leaf node with AWS resource icon + label.
  - Container nesting driven by `parentId` returned from the API.
  - dagre layout applied per-container, then globally.
- **Hover tooltip**: Show resource ID, Name, Region, Type on mouse-over.
- **Click detail panel**: Click any node to open `DetailPanel` with full
  `configuration` and `tags`.

### Test List

| ID | Test | Target |
|---|---|---|
| BF-01 | `Sidebar` fetches snapshot list from `GET /api/snapshots` and renders it | `Sidebar.tsx` |
| BF-02 | Selecting a snapshot calls `GET /api/snapshots/{id}/graph` | `App.tsx` / `api.ts` |
| BF-03 | `GraphCanvas` renders correct number of nodes and edges | `GraphCanvas.tsx` |
| BF-04 | `AwsNode` shows tooltip on hover (ID / Name / Type) | `AwsNode.tsx` |
| BF-05 | Clicking `AwsNode` opens `DetailPanel` | `App.tsx` |
| BF-06 | `DetailPanel` calls `GET /api/snapshots/{id}/resources/{rid}` and shows detail | `DetailPanel.tsx` |
| BF-07 | Changing resource type filter triggers graph API re-fetch | `Sidebar.tsx` |
| BF-08 | `applyDagreLayout()` assigns `position` to all nodes (compound graph support) | `utils/layout.ts` |
| BF-09 | `icons.ts` returns fallback URL for unknown resource type | `utils/icons.ts` |
| BF-10 | TB/LR layout toggle calls `applyDagreLayout` with correct `rankdir` | `Sidebar.tsx` |
| BF-11 | `AwsGroupNode` renders with dashed border and label | `AwsGroupNode.tsx` |
| BF-12 | Nodes with `parentId` are rendered inside their parent container | `GraphCanvas.tsx` |

### Red-Green-Refactor Order

1. BF-08 -> `applyDagreLayout()` (pure function, compound graph)
2. BF-09 -> `icons.ts` fallback
3. BF-11 -> `AwsGroupNode` container box rendering
4. BF-01 -> `Sidebar` with MSW mock
5. BF-02 -> snapshot selection -> graph API call
6. BF-03 + BF-12 -> `GraphCanvas` with compound nodes
7. BF-04 -> `AwsNode` hover tooltip
8. BF-05 -> click -> `DetailPanel` open
9. BF-06 -> `DetailPanel` detail fetch
10. BF-07 -> filter re-fetch
11. BF-10 -> layout toggle

---

## Phase C: Docker Integration

**Status: ✅ Complete**

| Task | File | Status |
|---|---|---|
| Multi-stage Dockerfile (Node build → Python runtime) | `config_viz/Dockerfile` | ✅ Done |
| Add `config-viz` service to docker-compose.yml | `docker/docker-compose.yml` | ✅ Done |
| AWS icon extraction script (run at build time) | `config_viz/backend/scripts/extract_icons.py` | ✅ Done |
| `/icons` static mount in FastAPI | `config_viz/backend/main.py` | ✅ Done |

---

## Implementation Timeline

```
Phase A:  FastAPI backend — BA-01 〜 BA-14 (all tests green)
Phase B:  React frontend  — BF-01 〜 BF-12 (all tests green)
Phase C:  Docker          — Dockerfile + docker-compose integration
```
