"""Phase A backend tests — BA-01 to BA-14.

All tests follow the TDD Red-Green-Refactor cycle:
  Red   : written here before any implementation exists.
  Green : backend/ modules are added to make each test pass.
"""

import pytest

# ---------------------------------------------------------------------------
# BA-01: Empty DB → GET /api/snapshots returns []
# ---------------------------------------------------------------------------


def test_ba01_empty_db_snapshots_returns_empty_list(client_empty):
    response = client_empty.get("/api/snapshots")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# BA-02: One ingested snapshot → /api/snapshots returns exactly 1 item
# ---------------------------------------------------------------------------


def test_ba02_one_snapshot_returns_one_item(client_seeded):
    response = client_seeded.get("/api/snapshots")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["snapshot_id"] == "snap-001"
    assert data[0]["account_id"] == "123456789012"
    assert data[0]["aws_region"] == "ap-northeast-1"
    assert data[0]["record_count"] == 2


# ---------------------------------------------------------------------------
# BA-03: /api/snapshots/{id}/resource-types returns the correct type list
# ---------------------------------------------------------------------------


def test_ba03_resource_types_returns_correct_list(client_seeded):
    response = client_seeded.get("/api/snapshots/snap-001/resource-types")
    assert response.status_code == 200
    types = response.json()
    assert isinstance(types, list)
    assert "AWS::EC2::Instance" in types
    assert "AWS::EC2::SecurityGroup" in types


# ---------------------------------------------------------------------------
# BA-04: /api/snapshots/{id}/graph — node count matches resource count
# ---------------------------------------------------------------------------


def test_ba04_graph_node_count_matches_resources(client_seeded):
    response = client_seeded.get("/api/snapshots/snap-001/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    # 2 physical resources + 1 EC2 service-group virtual node = 3 total
    assert len(data["nodes"]) == 3
    node_ids = {n["id"] for n in data["nodes"]}
    assert "i-12345" in node_ids
    assert "sg-aaaa" in node_ids
    assert "__svc__EC2" in node_ids


# ---------------------------------------------------------------------------
# BA-05: /api/snapshots/{id}/graph — edges exclude dangling references
# ---------------------------------------------------------------------------


def test_ba05_graph_edges_exclude_dangling(client_seeded):
    response = client_seeded.get("/api/snapshots/snap-001/graph")
    assert response.status_code == 200
    data = response.json()
    edges = data["edges"]
    # snap-001 has exactly 1 intra-snapshot edge (i-12345 → sg-aaaa)
    assert len(edges) == 1
    assert edges[0]["source"] == "i-12345"
    assert edges[0]["target"] == "sg-aaaa"
    assert edges[0]["label"] == "Is associated with"


# ---------------------------------------------------------------------------
# BA-06: /api/snapshots/{id}/resources/{rid} returns configuration + tags
# ---------------------------------------------------------------------------


def test_ba06_resource_detail_returns_configuration_and_tags(client_seeded):
    response = client_seeded.get("/api/snapshots/snap-001/resources/i-12345")
    assert response.status_code == 200
    data = response.json()
    assert data["resource_id"] == "i-12345"
    assert data["resource_type"] == "AWS::EC2::Instance"
    # configuration is returned as a parsed JSON object
    assert isinstance(data["configuration"], dict)
    assert data["configuration"]["instanceType"] == "t3.micro"
    # tags is a non-null dict for i-12345
    assert isinstance(data["tags"], dict)
    assert data["tags"]["Name"] == "web-server"


def test_ba06_resource_detail_null_tags_returns_none(client_seeded):
    # sg-aaaa was seeded with NULL tags
    response = client_seeded.get("/api/snapshots/snap-001/resources/sg-aaaa")
    assert response.status_code == 200
    data = response.json()
    assert data["resource_id"] == "sg-aaaa"
    assert data["tags"] is None


# ---------------------------------------------------------------------------
# BA-07: Non-existent snapshot_id returns 404 on all relevant endpoints
# ---------------------------------------------------------------------------


def test_ba07_nonexistent_snapshot_resource_types_returns_404(client_seeded):
    response = client_seeded.get("/api/snapshots/no-such-snap/resource-types")
    assert response.status_code == 404


def test_ba07_nonexistent_snapshot_graph_returns_404(client_seeded):
    response = client_seeded.get("/api/snapshots/no-such-snap/graph")
    assert response.status_code == 404


def test_ba07_nonexistent_snapshot_resource_detail_returns_404(client_seeded):
    response = client_seeded.get("/api/snapshots/no-such-snap/resources/i-12345")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# BA-08: resource_type= query param filters graph nodes
# ---------------------------------------------------------------------------


def test_ba08_resource_type_filter_applies_to_graph_nodes(client_seeded):
    response = client_seeded.get(
        "/api/snapshots/snap-001/graph?resource_type=AWS::EC2::Instance"
    )
    assert response.status_code == 200
    data = response.json()
    # Filtered view: no service-group virtual nodes, only 1 physical resource
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "i-12345"
    assert data["nodes"][0]["data"]["resource_type"] == "AWS::EC2::Instance"


def test_ba08_resource_type_filter_excludes_cross_type_edges(client_seeded):
    # When filtering to only Instance nodes, the edge to sg-aaaa (SecurityGroup)
    # disappears because sg-aaaa is not in the filtered node set.
    response = client_seeded.get(
        "/api/snapshots/snap-001/graph?resource_type=AWS::EC2::Instance"
    )
    assert response.status_code == 200
    data = response.json()
    # sg-aaaa is outside the filtered set → edge must be excluded
    assert len(data["edges"]) == 0


# ---------------------------------------------------------------------------
# BA-09: limit= query param caps the number of returned nodes
# ---------------------------------------------------------------------------


def test_ba09_limit_caps_node_count(client_seeded):
    response = client_seeded.get("/api/snapshots/snap-001/graph?limit=1")
    assert response.status_code == 200
    data = response.json()
    # limit caps physical resource nodes; service-group virtual nodes are always added
    physical = [n for n in data["nodes"] if not n["id"].startswith("__svc__")]
    assert len(physical) <= 1


# ---------------------------------------------------------------------------
# BA-10: validate_sql rejects write / DDL keywords (READ_ONLY blocklist)
# ---------------------------------------------------------------------------


def test_ba10_blocklist_rejects_drop(client_seeded):
    from backend.query import QueryValidationError, validate_sql

    with pytest.raises(QueryValidationError, match="not allowed"):
        validate_sql("DROP TABLE config_snapshots")


def test_ba10_blocklist_rejects_insert(client_seeded):
    from backend.query import QueryValidationError, validate_sql

    with pytest.raises(QueryValidationError, match="not allowed"):
        validate_sql(
            "INSERT INTO config_snapshots VALUES ('x', null, null, null, null, 0)"
        )


def test_ba10_blocklist_rejects_delete(client_seeded):
    from backend.query import QueryValidationError, validate_sql

    with pytest.raises(QueryValidationError, match="not allowed"):
        validate_sql("DELETE FROM config_resources")


def test_ba10_blocklist_rejects_create(client_seeded):
    from backend.query import QueryValidationError, validate_sql

    with pytest.raises(QueryValidationError, match="not allowed"):
        validate_sql("CREATE TABLE evil (x VARCHAR)")


def test_ba10_blocklist_allows_select(client_seeded):
    from backend.query import validate_sql

    # Must NOT raise — plain SELECT is allowed
    validate_sql("SELECT * FROM config_snapshots")


# ---------------------------------------------------------------------------
# BA-11: Hierarchy — graph nodes carry parentId and is_container metadata
# ---------------------------------------------------------------------------


def test_ba11_vpc_node_has_no_parent(client_hierarchy):
    """Root container (VPC) must be placed inside the EC2 service-group node."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    assert response.status_code == 200
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    # With service groups, VPC is inside __svc__EC2, not at the root
    assert nodes["vpc-001"]["parentId"] == "__svc__EC2"


def test_ba11_subnet_node_parent_is_vpc(client_hierarchy):
    """Subnet node parentId must equal its containing VPC."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert nodes["subnet-001"]["parentId"] == "vpc-001"


def test_ba11_instance_node_parent_is_subnet(client_hierarchy):
    """EC2 Instance node parentId must equal its containing Subnet."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert nodes["i-001"]["parentId"] == "subnet-001"


def test_ba11_vpc_and_subnet_flagged_as_containers(client_hierarchy):
    """VPC and Subnet must have is_container=True; Instance and SG must be False."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert nodes["vpc-001"]["data"]["is_container"] is True
    assert nodes["subnet-001"]["data"]["is_container"] is True
    assert nodes["i-001"]["data"]["is_container"] is False
    assert nodes["sg-001"]["data"]["is_container"] is False


def test_ba11_container_nodes_use_awsGroupNode_type(client_hierarchy):
    """Container nodes must have type='awsGroupNode'; leaves must be 'awsNode'."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert nodes["vpc-001"]["type"] == "awsGroupNode"
    assert nodes["subnet-001"]["type"] == "awsGroupNode"
    assert nodes["i-001"]["type"] == "awsNode"
    assert nodes["sg-001"]["type"] == "awsNode"


def test_ba11_contains_edges_excluded_from_edge_list(client_hierarchy):
    """'Contains' edges must NOT appear in the edges list (expressed via parentId)."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    data = response.json()
    labels = [e["label"] for e in data["edges"]]
    assert "Contains" not in labels, "containment edges must be removed from edge list"


def test_ba11_association_edge_still_present(client_hierarchy):
    """Non-containment edges ('Is associated with') must remain in the edge list."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    data = response.json()
    labels = [e["label"] for e in data["edges"]]
    assert "Is associated with" in labels


def test_ba11_parent_outside_filtered_set_is_null(client_hierarchy):
    """When resource_type filter excludes the parent, parentId must be None."""
    # Filter to only EC2::Instance; its parent (Subnet) is excluded
    response = client_hierarchy.get(
        "/api/snapshots/snap-002/graph?resource_type=AWS::EC2::Instance"
    )
    assert response.status_code == 200
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert (
        nodes["i-001"]["parentId"] is None
    ), "parent (subnet-001) is not in the filtered set, so parentId must be None"


# ---------------------------------------------------------------------------
# BA-12: config_snapshots table missing → /api/snapshots returns [] (not 500)
#
# This covers the case where config-import has never been run.
# The cloudtrail_events table exists but the Config tables do not.
# ---------------------------------------------------------------------------


@pytest.fixture
def client_no_config_tables(tmp_path):
    """TestClient backed by a DB that has NO config_* tables (only CloudTrail)."""
    import duckdb
    from fastapi.testclient import TestClient
    from backend.db import get_conn
    from backend.main import app

    db_path = str(tmp_path / "no_config.db")
    conn = duckdb.connect(db_path)
    # Only create the cloudtrail table — config tables are intentionally absent
    conn.execute(
        "CREATE TABLE cloudtrail_events (event_time TIMESTAMP, event_name VARCHAR)"
    )
    conn.close()

    def override_conn():
        c = duckdb.connect(db_path, read_only=True)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override_conn
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_ba12_no_config_tables_snapshots_returns_empty_list(client_no_config_tables):
    """GET /api/snapshots returns 200 [] when config_snapshots table does not exist."""
    response = client_no_config_tables.get("/api/snapshots")
    assert response.status_code == 200
    assert response.json() == []


def test_ba12_no_config_tables_snapshot_id_returns_404(client_no_config_tables):
    """GET /api/snapshots/{id}/resource-types returns 404 when tables don't exist."""
    response = client_no_config_tables.get("/api/snapshots/snap-xxx/resource-types")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# BA-13: Service-group virtual nodes — full (unfiltered) graph response
# ---------------------------------------------------------------------------


def test_ba13_service_group_node_present_in_full_graph(client_seeded):
    """Full graph must include a service-group virtual node for EC2."""
    response = client_seeded.get("/api/snapshots/snap-001/graph")
    assert response.status_code == 200
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert "__svc__EC2" in nodes, "EC2 service-group node must be present"
    svc = nodes["__svc__EC2"]
    assert svc["type"] == "awsGroupNode"
    assert svc["parentId"] is None
    assert svc["data"]["is_container"] is True


def test_ba13_physical_resources_have_service_group_as_parent(client_seeded):
    """i-12345 and sg-aaaa must both have __svc__EC2 as parentId."""
    response = client_seeded.get("/api/snapshots/snap-001/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert nodes["i-12345"]["parentId"] == "__svc__EC2"
    assert nodes["sg-aaaa"]["parentId"] == "__svc__EC2"


def test_ba13_service_group_absent_in_filtered_view(client_seeded):
    """Filtered view must NOT include service-group virtual nodes."""
    response = client_seeded.get(
        "/api/snapshots/snap-001/graph?resource_type=AWS::EC2::Instance"
    )
    assert response.status_code == 200
    node_ids = {n["id"] for n in response.json()["nodes"]}
    assert "__svc__EC2" not in node_ids


# ---------------------------------------------------------------------------
# BA-14: Partial-match containment edges ("Contains Subnet", "Is contained in Vpc")
# ---------------------------------------------------------------------------


def test_ba14_contains_subnet_edge_sets_parentid(client_hierarchy):
    """'Contains Subnet' edge type must resolve subnet-001 parentId = vpc-001."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    # The fixture uses "Contains Subnet" (not bare "Contains")
    assert (
        nodes["subnet-001"]["parentId"] == "vpc-001"
    ), "'Contains Subnet' must be recognised as a containment edge"


def test_ba14_service_group_is_top_level_for_vpc(client_hierarchy):
    """The EC2 service-group node must be the outermost container in snap-002."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert "__svc__EC2" in nodes
    assert nodes["__svc__EC2"]["parentId"] is None


def test_ba14_hierarchy_depth_is_correct(client_hierarchy):
    """Full containment chain: __svc__EC2 → vpc-001 → subnet-001 → i-001."""
    response = client_hierarchy.get("/api/snapshots/snap-002/graph")
    nodes = {n["id"]: n for n in response.json()["nodes"]}
    assert nodes["vpc-001"]["parentId"] == "__svc__EC2"
    assert nodes["subnet-001"]["parentId"] == "vpc-001"
    assert nodes["i-001"]["parentId"] == "subnet-001"
