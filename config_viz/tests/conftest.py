"""Shared pytest fixtures for config_viz backend tests.

Each test that needs a database gets a fresh temporary DuckDB file so
tests remain fully isolated.
"""

import duckdb
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS config_snapshots (
        snapshot_id  VARCHAR PRIMARY KEY,
        account_id   VARCHAR,
        aws_region   VARCHAR,
        captured_at  TIMESTAMP,
        source_path  VARCHAR,
        record_count INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS config_resources (
        resource_id   VARCHAR,
        snapshot_id   VARCHAR,
        resource_type VARCHAR,
        aws_region    VARCHAR,
        resource_name VARCHAR,
        configuration VARCHAR,
        tags          VARCHAR,
        PRIMARY KEY (resource_id, resource_type, snapshot_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS config_edges (
        snapshot_id VARCHAR,
        source_id   VARCHAR,
        target_id   VARCHAR,
        edge_type   VARCHAR,
        PRIMARY KEY (snapshot_id, source_id, target_id, edge_type)
    )
    """,
]


def _create_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Execute all CREATE TABLE statements on *conn*."""
    for ddl in _CREATE_TABLES_SQL:
        conn.execute(ddl)


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert mini snapshot data: snap-001, 2 resources, 1 edge."""
    conn.execute("""
        INSERT INTO config_snapshots VALUES
            ('snap-001', '123456789012', 'ap-northeast-1',
             TIMESTAMP '2026-01-01 00:00:00', '/data/snap.json', 2)
        """)
    conn.execute("""
        INSERT INTO config_resources VALUES
            ('i-12345', 'snap-001', 'AWS::EC2::Instance',
             'ap-northeast-1', 'web-server',
             '{"instanceType":"t3.micro"}', '{"Name":"web-server"}'),
            ('sg-aaaa', 'snap-001', 'AWS::EC2::SecurityGroup',
             'ap-northeast-1', 'web-sg',
             '{"groupId":"sg-aaaa"}', NULL)
        """)
    conn.execute("""
        INSERT INTO config_edges VALUES
            ('snap-001', 'i-12345', 'sg-aaaa', 'Is associated with')
        """)


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_empty(tmp_path) -> str:
    """Temporary DuckDB with empty config tables."""
    path = str(tmp_path / "empty.db")
    conn = duckdb.connect(path)
    _create_tables(conn)
    conn.close()
    return path


@pytest.fixture
def tmp_db_seeded(tmp_path) -> str:
    """Temporary DuckDB seeded with snap-001 (2 resources, 1 edge)."""
    path = str(tmp_path / "seeded.db")
    conn = duckdb.connect(path)
    _create_tables(conn)
    _seed(conn)
    conn.close()
    return path


# ---------------------------------------------------------------------------
# TestClient fixtures
# ---------------------------------------------------------------------------


def _seed_hierarchy(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert hierarchy snapshot: snap-002 with VPC → Subnet → EC2 containment.

    Resources
    ---------
    vpc-001    AWS::EC2::VPC         (root — no parent)
    subnet-001 AWS::EC2::Subnet      (contained in vpc-001)
    i-001      AWS::EC2::Instance    (contained in subnet-001)
    sg-001     AWS::EC2::SecurityGroup (NOT a container — associated with i-001)

    Edges  — uses real AWS Config edge-type strings (partial-match format)
    -----------------------------------------
    vpc-001    → subnet-001   "Contains Subnet"
    subnet-001 → i-001        "Contains"
    i-001      → sg-001       "Is associated with"
    """
    conn.execute("""
        INSERT INTO config_snapshots VALUES
            ('snap-002', '111122223333', 'ap-northeast-1',
             TIMESTAMP '2026-05-01 00:00:00', '/data/snap2.json', 4)
        """)
    conn.execute("""
        INSERT INTO config_resources VALUES
            ('vpc-001',    'snap-002', 'AWS::EC2::VPC',
             'ap-northeast-1', 'main-vpc',    '{"vpcId":"vpc-001"}',    NULL),
            ('subnet-001', 'snap-002', 'AWS::EC2::Subnet',
             'ap-northeast-1', 'public-sub',  '{"subnetId":"subnet-001"}', NULL),
            ('i-001',      'snap-002', 'AWS::EC2::Instance',
             'ap-northeast-1', 'app-server',  '{"instanceType":"t3.small"}', NULL),
            ('sg-001',     'snap-002', 'AWS::EC2::SecurityGroup',
             'ap-northeast-1', 'app-sg',      '{"groupId":"sg-001"}',  NULL)
        """)
    conn.execute("""
        INSERT INTO config_edges VALUES
            ('snap-002', 'vpc-001',    'subnet-001', 'Contains Subnet'),
            ('snap-002', 'subnet-001', 'i-001',      'Contains'),
            ('snap-002', 'i-001',      'sg-001',     'Is associated with')
        """)


def _make_override(db_path: str):
    """Return a FastAPI dependency override that opens *db_path* READ_ONLY."""

    def override_conn():
        conn = duckdb.connect(db_path, read_only=True)
        try:
            yield conn
        finally:
            conn.close()

    return override_conn


@pytest.fixture
def tmp_db_hierarchy(tmp_path) -> str:
    """Temporary DuckDB seeded with snap-002 (VPC → Subnet → EC2 hierarchy)."""
    path = str(tmp_path / "hierarchy.db")
    conn = duckdb.connect(path)
    _create_tables(conn)
    _seed_hierarchy(conn)
    conn.close()
    return path


@pytest.fixture
def client_hierarchy(tmp_db_hierarchy):
    """TestClient backed by the hierarchy DB (snap-002, 4 resources, 3 edges)."""
    from backend.db import get_conn
    from backend.main import app

    app.dependency_overrides[get_conn] = _make_override(tmp_db_hierarchy)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client_empty(tmp_db_empty):
    """TestClient backed by an empty config DB."""
    from backend.db import get_conn
    from backend.main import app

    app.dependency_overrides[get_conn] = _make_override(tmp_db_empty)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client_seeded(tmp_db_seeded):
    """TestClient backed by snap-001 (2 resources: Instance + SecurityGroup, 1 edge)."""
    from backend.db import get_conn
    from backend.main import app

    app.dependency_overrides[get_conn] = _make_override(tmp_db_seeded)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
