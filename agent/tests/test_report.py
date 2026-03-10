"""Tests for report.py — Threat hunting report generation."""

import pandas as pd

from report import ReportEntry, generate_report


def test_generate_report_markdown():
    """Given a session (queries + results + analysis), generates a Markdown report."""
    entry = ReportEntry(
        sql="SELECT event_name FROM cloudtrail_events LIMIT 5",
        results=pd.DataFrame({"event_name": ["CreateUser", "DescribeInstances"]}),
        analysis="Two events were found.",
    )

    report = generate_report([entry])

    assert isinstance(report, str)
    assert len(report) > 0
    assert "SELECT" in report


def test_report_includes_timestamp():
    """The report header includes the generation timestamp."""
    entry = ReportEntry(
        sql="SELECT 1",
        results=pd.DataFrame(),
        analysis="No results.",
    )

    report = generate_report([entry])

    # ISO 8601 date portion (YYYY-MM-DD) must appear in the header
    assert "2026-03-11" in report


def test_report_includes_all_queries():
    """Each query-result-analysis triple is included in the report."""
    entries = [
        ReportEntry(
            sql="SELECT event_name FROM cloudtrail_events LIMIT 1",
            results=pd.DataFrame({"event_name": ["CreateUser"]}),
            analysis="First analysis.",
        ),
        ReportEntry(
            sql="SELECT aws_region FROM cloudtrail_events LIMIT 1",
            results=pd.DataFrame({"aws_region": ["us-east-1"]}),
            analysis="Second analysis.",
        ),
    ]

    report = generate_report(entries)

    assert "SELECT event_name FROM cloudtrail_events LIMIT 1" in report
    assert "SELECT aws_region FROM cloudtrail_events LIMIT 1" in report
    assert "First analysis." in report
    assert "Second analysis." in report


def test_report_sanitizes_sensitive_data():
    """API keys or credentials in query results are redacted."""
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

