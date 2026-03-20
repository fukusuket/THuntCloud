"""Tests for Superset chart YAML files.

Validates that every chart YAML in cloudtrail_default/charts/ conforms to
the structure required by the Superset v1 dashboard import format.
"""
import os
import re

import pytest
import yaml

CHARTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "assets", "cloudtrail_default", "charts"
)
DATASET_UUID = "d8444b4a-ac55-4710-a777-a5b940bebabe"
REQUIRED_CHART_FIELDS = {"uuid", "version", "dataset_uuid", "slice_name", "viz_type", "params"}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_all_charts() -> list[tuple[str, dict]]:
    """Return (filename, parsed_yaml) for every .yaml in charts/."""
    results = []
    for fname in sorted(os.listdir(CHARTS_DIR)):
        if fname.endswith(".yaml"):
            path = os.path.join(CHARTS_DIR, fname)
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            results.append((fname, data))
    return results


# ---------------------------------------------------------------------------
# Parametric tests — run once per chart file
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fname, chart", load_all_charts())
def test_chart_has_required_fields(fname: str, chart: dict) -> None:
    """Every chart must declare all required top-level fields."""
    missing = REQUIRED_CHART_FIELDS - set(chart.keys())
    assert not missing, f"{fname} is missing fields: {missing}"


@pytest.mark.parametrize("fname, chart", load_all_charts())
def test_chart_dataset_uuid(fname: str, chart: dict) -> None:
    """Every chart must reference the canonical cloudtrail_events dataset."""
    assert chart.get("dataset_uuid") == DATASET_UUID, (
        f"{fname}: dataset_uuid mismatch — got '{chart.get('dataset_uuid')}', "
        f"expected '{DATASET_UUID}'"
    )


@pytest.mark.parametrize("fname, chart", load_all_charts())
def test_chart_uuid_format(fname: str, chart: dict) -> None:
    """Chart UUID must be a valid lowercase UUID v4 string."""
    uuid = chart.get("uuid", "")
    assert UUID_RE.match(uuid), f"{fname}: '{uuid}' is not a valid UUID"


@pytest.mark.parametrize("fname, chart", load_all_charts())
def test_chart_params_not_empty(fname: str, chart: dict) -> None:
    """params must be a non-empty mapping."""
    assert chart.get("params"), f"{fname}: params must not be empty"


# ---------------------------------------------------------------------------
# Global tests
# ---------------------------------------------------------------------------

# Valid aggregator names accepted by React Pivottable (used in Superset pivot_table_v2).
# Superset throws "this.props.aggregatorsFactory(...)[this.props.aggregatorName] is not a
# function" when this value is not an exact case-sensitive match.
_VALID_AGGREGATE_FUNCTIONS: frozenset[str] = frozenset({
    "Count", "Count Unique Values", "List Unique Values",
    "Sum", "Integer Sum", "Average", "Median",
    "Sample Variance", "Sample Standard Deviation",
    "Minimum", "Maximum", "First", "Last",
    "Sum as Fraction of Total", "Sum as Fraction of Rows",
    "Sum as Fraction of Columns", "Count as Fraction of Total",
    "Count as Fraction of Rows", "Count as Fraction of Columns",
})


def test_pivot_table_aggregate_function_valid() -> None:
    """pivot_table_v2 charts must use a valid React Pivottable aggregator name.

    Using an invalid name (e.g. 'SUM' instead of 'Sum') causes:
      TypeError: this.props.aggregatorsFactory(...)[this.props.aggregatorName]
                 is not a function
    """
    offenders = []
    for fname, chart in load_all_charts():
        if chart.get("viz_type") != "pivot_table_v2":
            continue
        agg = chart.get("params", {}).get("aggregateFunction")
        if agg is not None and agg not in _VALID_AGGREGATE_FUNCTIONS:
            offenders.append((fname, agg))
    assert not offenders, (
        f"pivot_table_v2 charts have invalid aggregateFunction: {offenders}\n"
        f"Valid values: {sorted(_VALID_AGGREGATE_FUNCTIONS)}"
    )


def test_all_chart_uuids_unique() -> None:
    """No two chart files may share the same UUID."""
    charts = load_all_charts()
    uuids = [c["uuid"] for _, c in charts]
    duplicates = {u for u in uuids if uuids.count(u) > 1}
    assert not duplicates, f"Duplicate chart UUIDs detected: {duplicates}"


# ---------------------------------------------------------------------------
# Sprint-1 mandatory charts
# ---------------------------------------------------------------------------

def _find_chart_by_filename(fragment: str) -> tuple[str, dict] | None:
    for fname, chart in load_all_charts():
        if fragment in fname.lower():
            return fname, chart
    return None


def test_dsh22_defense_evasion_exists() -> None:
    """DSH-22: defense_evasion.yaml must exist with correct metadata."""
    result = _find_chart_by_filename("defense_evasion")
    assert result is not None, "charts/defense_evasion.yaml not found"
    _, chart = result
    assert chart["viz_type"] == "table"
    assert "Defense Evasion" in chart["slice_name"]


def test_dsh28_mfa_less_login_trend_exists() -> None:
    """DSH-28: mfa_less_login_trend.yaml must exist with correct metadata."""
    result = _find_chart_by_filename("mfa_less_login_trend")
    assert result is not None, "charts/mfa_less_login_trend.yaml not found"
    _, chart = result
    assert chart["viz_type"] == "echarts_timeseries_bar"
    assert "MFA" in chart["slice_name"]


# ---------------------------------------------------------------------------
# Sprint-2 charts
# ---------------------------------------------------------------------------

def test_dsh19_login_heatmap_exists() -> None:
    """DSH-19: login_heatmap.yaml must exist."""
    result = _find_chart_by_filename("login_heatmap")
    assert result is not None, "charts/login_heatmap.yaml not found"
    _, chart = result
    assert chart["viz_type"] in ("pivot_table_v2", "table")


def test_dsh20_write_read_ratio_exists() -> None:
    """DSH-20: write_read_ratio.yaml must exist."""
    result = _find_chart_by_filename("write_read_ratio")
    assert result is not None, "charts/write_read_ratio.yaml not found"
    _, chart = result
    assert chart["viz_type"] == "echarts_timeseries_bar"


def test_dsh21_throttling_spikes_exists() -> None:
    """DSH-21: throttling_spikes.yaml must exist."""
    result = _find_chart_by_filename("throttling_spikes")
    assert result is not None, "charts/throttling_spikes.yaml not found"
    _, chart = result
    assert chart["viz_type"] == "echarts_timeseries_bar"


# ---------------------------------------------------------------------------
# Sprint-3 charts
# ---------------------------------------------------------------------------

def test_dsh23_secrets_access_anomaly_exists() -> None:
    """DSH-23: secrets_access_anomaly.yaml must exist."""
    assert _find_chart_by_filename("secrets_access_anomaly") is not None


def test_dsh24_org_scp_changes_exists() -> None:
    """DSH-24: org_scp_changes.yaml must exist."""
    assert _find_chart_by_filename("org_scp_changes") is not None


def test_dsh27_assumed_role_external_ip_exists() -> None:
    """DSH-27: assumed_role_external_ip.yaml must exist."""
    assert _find_chart_by_filename("assumed_role_external_ip") is not None


def test_dsh30_priv_esc_timeline_exists() -> None:
    """DSH-30: priv_esc_timeline.yaml must exist."""
    assert _find_chart_by_filename("priv_esc_timeline") is not None


# ---------------------------------------------------------------------------
# Sprint-4 charts
# ---------------------------------------------------------------------------

def test_dsh25_s3_protection_changes_exists() -> None:
    """DSH-25: s3_protection_changes.yaml must exist."""
    assert _find_chart_by_filename("s3_protection_changes") is not None


def test_dsh26_first_time_services_exists() -> None:
    """DSH-26: first_time_services.yaml must exist."""
    assert _find_chart_by_filename("first_time_services") is not None


def test_dsh29_route53_dns_changes_exists() -> None:
    """DSH-29: route53_dns_changes.yaml must exist."""
    assert _find_chart_by_filename("route53_dns_changes") is not None

