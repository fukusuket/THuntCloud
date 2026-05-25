"""Tests for dashboard.yaml structure and chart cross-references.

Ensures that every chart YAML file is referenced in the dashboard layout,
and that every layout entry has a corresponding YAML file on disk.
"""

import os

import pytest
import yaml

CHARTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "assets", "cloudtrail_default", "charts"
)
DASHBOARD_YAML_PATH = os.path.join(
    os.path.dirname(__file__), "..", "assets", "cloudtrail_default", "dashboard.yaml"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_dashboard() -> dict:
    with open(DASHBOARD_YAML_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_chart_uuids_from_dashboard(dashboard: dict) -> set[str]:
    """Extract all chart UUIDs from the dashboard position layout."""
    uuids: set[str] = set()
    for value in dashboard.get("position", {}).values():
        if isinstance(value, dict) and value.get("type") == "CHART":
            meta = value.get("meta", {})
            if "uuid" in meta:
                uuids.add(meta["uuid"])
    return uuids


def get_chart_uuids_from_files() -> dict[str, str]:
    """Return {uuid: filename} for all chart YAML files."""
    result: dict[str, str] = {}
    for fname in os.listdir(CHARTS_DIR):
        if not fname.endswith(".yaml"):
            continue
        with open(os.path.join(CHARTS_DIR, fname), encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        result[data["uuid"]] = fname
    return result


# ---------------------------------------------------------------------------
# dashboard.yaml structural tests
# ---------------------------------------------------------------------------


def test_dashboard_yaml_exists() -> None:
    assert os.path.exists(DASHBOARD_YAML_PATH), "dashboard.yaml not found"


def test_all_chart_components_have_children_list() -> None:
    """Every CHART in position must have children: [] so Superset can call .forEach().

    Without this property the Superset frontend throws:
      TypeError: Cannot read properties of undefined (reading 'forEach')
    """
    dashboard = load_dashboard()
    offenders = [
        key
        for key, val in dashboard.get("position", {}).items()
        if isinstance(val, dict)
        and val.get("type") == "CHART"
        and not isinstance(val.get("children"), list)
    ]
    assert not offenders, (
        f"CHART components missing 'children: []': {offenders}\n"
        "Add 'children: []' to each CHART entry in dashboard.yaml."
    )


def test_dashboard_has_required_keys() -> None:
    dashboard = load_dashboard()
    required = {"uuid", "version", "dashboard_title", "position", "metadata"}
    missing = required - set(dashboard.keys())
    assert not missing, f"dashboard.yaml missing fields: {missing}"


def test_dashboard_filter_ids_unique() -> None:
    """Native filter IDs must be unique within the dashboard."""
    dashboard = load_dashboard()
    filter_configs = dashboard.get("metadata", {}).get(
        "native_filter_configuration", []
    )
    ids = [f["id"] for f in filter_configs]
    assert len(ids) == len(
        set(ids)
    ), "Duplicate filter IDs in native_filter_configuration"


def test_dashboard_has_tab_layout() -> None:
    """dashboard.yaml must use a TABS layout (4 tabs)."""
    dashboard = load_dashboard()
    position = dashboard.get("position", {})
    tab_entries = [
        v for v in position.values() if isinstance(v, dict) and v.get("type") == "TAB"
    ]
    assert (
        len(tab_entries) >= 4
    ), f"Expected at least 4 TAB entries in position, found {len(tab_entries)}"


# ---------------------------------------------------------------------------
# Cross-reference tests
# ---------------------------------------------------------------------------


def test_dashboard_chart_uuids_have_matching_yaml() -> None:
    """Every chart UUID in dashboard.yaml must have a matching chart YAML file."""
    dashboard = load_dashboard()
    dashboard_uuids = get_chart_uuids_from_dashboard(dashboard)
    file_uuids = get_chart_uuids_from_files()
    missing = dashboard_uuids - set(file_uuids.keys())
    assert (
        not missing
    ), f"Chart UUIDs in dashboard.yaml with no matching YAML file: {missing}"


def test_all_chart_yamls_referenced_in_dashboard() -> None:
    """Every chart YAML file must be referenced in the dashboard layout."""
    dashboard = load_dashboard()
    dashboard_uuids = get_chart_uuids_from_dashboard(dashboard)
    file_uuids = get_chart_uuids_from_files()
    unreferenced = set(file_uuids.keys()) - dashboard_uuids
    unreferenced_files = {file_uuids[u] for u in unreferenced}
    assert (
        not unreferenced_files
    ), f"Chart YAML files not referenced in dashboard.yaml: {unreferenced_files}"


# ---------------------------------------------------------------------------
# New-chart presence in dashboard layout
# ---------------------------------------------------------------------------


def _uuid_for_chart_file(fragment: str) -> str | None:
    for fname in os.listdir(CHARTS_DIR):
        if fragment in fname.lower() and fname.endswith(".yaml"):
            with open(os.path.join(CHARTS_DIR, fname), encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            return data.get("uuid")
    return None


@pytest.mark.parametrize(
    "fragment,label",
    [
        ("defense_evasion", "DSH-22 Defense Evasion"),
        ("mfa_less_login_trend", "DSH-28 MFA-less Login Trend"),
        ("login_heatmap", "DSH-19 Login Heatmap"),
        ("write_read_ratio", "DSH-20 Write/Read Ratio"),
        ("throttling_spikes", "DSH-21 Throttling Spikes"),
        ("secrets_access_anomaly", "DSH-23 Secrets Access Anomaly"),
        ("org_scp_changes", "DSH-24 Org/SCP Changes"),
        ("s3_protection_changes", "DSH-25 S3 Protection Changes"),
        ("first_time_services", "DSH-26 First-Time Services"),
        ("assumed_role_external", "DSH-27 AssumedRole External IP"),
        ("priv_esc_timeline", "DSH-30 Privilege Escalation Timeline"),
        ("route53_dns_changes", "DSH-29 Route53 DNS Changes"),
        # Sprint-5 — High-Risk API Monitor
        ("hrm_timeseries", "HRM-39 High-Risk API Timeseries"),
        ("hrm_top_calls", "HRM-40 High-Risk Top API Calls"),
        ("hrm_top_actors", "HRM-42 High-Risk Top Actors"),
        ("hrm_top_source_ips", "HRM-43 High-Risk Top Source IPs"),
        ("hrm_defense_evasion_table", "HRM-44 High-Risk Defense Evasion Table"),
        ("hrm_credential_access_table", "HRM-45 High-Risk Credential Access Table"),
        ("hrm_by_region", "HRM-46 High-Risk API by Region"),
    ],
)
def test_new_chart_referenced_in_dashboard(fragment: str, label: str) -> None:
    uuid = _uuid_for_chart_file(fragment)
    assert (
        uuid is not None
    ), f"{label}: chart YAML file not found (fragment='{fragment}')"
    dashboard = load_dashboard()
    dashboard_uuids = get_chart_uuids_from_dashboard(dashboard)
    assert (
        uuid in dashboard_uuids
    ), f"{label} (uuid={uuid}) not referenced in dashboard.yaml"


# ---------------------------------------------------------------------------
# New native filters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filter_id,description",
    [
        ("NATIVE_FILTER-identity-type", "Identity Type filter"),
        ("NATIVE_FILTER-identity-type-not", "Identity Type NOT filter"),
        ("NATIVE_FILTER-region", "AWS Region filter"),
        ("NATIVE_FILTER-region-not", "AWS Region NOT filter"),
        ("NATIVE_FILTER-error-code", "Error Code filter"),
        ("NATIVE_FILTER-error-code-not", "Error Code NOT filter"),
        ("NATIVE_FILTER-read-only", "Write/Read filter"),
        ("NATIVE_FILTER-read-only-not", "Write/Read NOT filter"),
        ("NATIVE_FILTER-arn", "Principal ARN filter"),
        ("NATIVE_FILTER-arn-not", "Principal ARN NOT filter"),
        ("NATIVE_FILTER-user-agent", "User Agent filter"),
        ("NATIVE_FILTER-user-agent-not", "User Agent NOT filter"),
    ],
)
def test_new_native_filter_exists(filter_id: str, description: str) -> None:
    dashboard = load_dashboard()
    filter_ids = {
        f["id"]
        for f in dashboard.get("metadata", {}).get("native_filter_configuration", [])
    }
    assert (
        filter_id in filter_ids
    ), f"{description} (id='{filter_id}') not found in dashboard.yaml"
