"""Tests for report.py — Threat hunting report generation."""

from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

from report import ReportEntry, generate_report


def test_generate_report_markdown():
    """Given a session (queries + results + summary), generates a Markdown report."""
    entry = ReportEntry(
        sql="SELECT event_name FROM cloudtrail_events LIMIT 5",
        results=pd.DataFrame({"event_name": ["CreateUser", "DescribeInstances"]}),
        analysis="- 2 events found.\n- CreateUser: 1, DescribeInstances: 1.",
    )

    report = generate_report([entry])

    assert isinstance(report, str)
    assert len(report) > 0
    assert "SELECT" in report
    # Summary section must appear; legacy "### Analysis" heading must NOT
    assert "### Summary" in report
    assert "### Analysis" not in report


def test_report_includes_timestamp():
    """The report header includes the generation timestamp."""
    entry = ReportEntry(
        sql="SELECT 1",
        results=pd.DataFrame(),
        analysis="",
    )

    fixed_dt = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)
    with patch("report.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_dt
        report = generate_report([entry])

    # ISO 8601 date portion (YYYY-MM-DD) must appear in the header
    assert "2026-03-11" in report


def test_report_includes_all_queries():
    """Each query-result-summary triple is included in the report."""
    entries = [
        ReportEntry(
            sql="SELECT event_name FROM cloudtrail_events LIMIT 1",
            results=pd.DataFrame({"event_name": ["CreateUser"]}),
            analysis="- 1 CreateUser event found.",
        ),
        ReportEntry(
            sql="SELECT aws_region FROM cloudtrail_events LIMIT 1",
            results=pd.DataFrame({"aws_region": ["us-east-1"]}),
            analysis="- 1 event in us-east-1.",
        ),
    ]

    report = generate_report(entries)

    assert "SELECT event_name FROM cloudtrail_events LIMIT 1" in report
    assert "SELECT aws_region FROM cloudtrail_events LIMIT 1" in report
    assert "1 CreateUser event found." in report
    assert "1 event in us-east-1." in report
    assert "### Summary" in report
    assert "### Analysis" not in report


def test_report_entry_chart_config_defaults_to_none():
    """ReportEntry.chart_config must default to None when not provided.

    Test #CHART-R1: backward-compatible — existing callers are unaffected.
    """
    entry = ReportEntry(sql="SELECT 1", results=pd.DataFrame())
    assert hasattr(entry, "chart_config"), (
        "ReportEntry must have a 'chart_config' field"
    )
    assert entry.chart_config is None


def test_report_entry_chart_config_stores_dict():
    """ReportEntry.chart_config must accept and persist a dict.

    Test #CHART-R2: verifies the field is writable with a chart config dict.
    """
    config = {"type": "bar", "x": "event_name", "y": ["api_count"]}
    entry = ReportEntry(sql="SELECT 1", results=pd.DataFrame(), chart_config=config)
    assert entry.chart_config == config


def test_report_sanitizes_sensitive_data():
    """Credentials in query results and summary text are redacted."""
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # 40-char secret-like string
    key_id = "AKIAIOSFODNN7EXAMPLE"  # AWS Access Key ID pattern

    entry = ReportEntry(
        sql="SELECT secret FROM credentials",
        results=pd.DataFrame({"secret": [secret], "key_id": [key_id]}),
        analysis=f"Found secret: {secret} and key: {key_id}",
    )

    report = generate_report([entry])

    assert secret not in report
    assert key_id not in report
    assert "REDACTED" in report
    assert "### Summary" in report
    assert "### Analysis" not in report
