"""Threat hunting report generation.

Generates structured Markdown reports from investigation sessions,
including queries, results, analysis, and sensitive data redaction.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

# ---------------------------------------------------------------------------
# Sensitive data redaction patterns
# ---------------------------------------------------------------------------
# Each entry is (compiled_pattern, replacement_string).
_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # AWS Access Key ID: AKIA/ASIA/AROA/AIDA followed by 16 uppercase alphanumerics
    (re.compile(r"(AKIA|ASIA|AROA|AIDA)[A-Z0-9]{16}"), "[REDACTED_KEY_ID]"),
    # AWS Secret Access Key: 40-character base64-like string (must come AFTER key ID
    # pattern so key IDs are not partially matched by this broader rule)
    (
        re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
        "[REDACTED_SECRET]",
    ),
]


def _sanitize(text: str) -> str:
    """Redact sensitive credential-like strings from a text block.

    Args:
        text: Arbitrary string that may contain AWS credentials.

    Returns:
        The input string with sensitive patterns replaced by redaction markers.
    """
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ReportEntry:
    """A single query-result-summary triple in an investigation session."""

    sql: str
    results: pd.DataFrame
    analysis: str = ""
    # Prevent pandas DataFrame equality issues in dataclass comparisons
    _results_placeholder: None = field(default=None, init=False, repr=False)


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------


def _render_entry(index: int, entry: ReportEntry) -> str:
    """Render one ReportEntry as a Markdown section.

    Outputs the SQL query, results table, and a fact-based summary.
    The summary contains only observed facts from the query results;
    speculative threat assessments are excluded by the LLM prompt.

    Args:
        index: 1-based query number used for the section heading.
        entry: The ReportEntry to render.

    Returns:
        A Markdown string for the given entry.
    """
    # Results table: render up to 1000 rows; fall back to "(no results)"
    if entry.results is not None and not entry.results.empty:
        results_md = entry.results.head(1000).to_markdown(index=False)
    else:
        results_md = "(no results)"

    sql_block = _sanitize(entry.sql)
    results_block = _sanitize(results_md)
    summary_block = _sanitize(entry.analysis) if entry.analysis else "(no summary)"

    return (
        f"## Query {index}\n\n"
        f"### SQL\n\n"
        f"```sql\n{sql_block}\n```\n\n"
        f"### Results\n\n"
        f"{results_block}\n\n"
        f"### Summary\n\n"
        f"{summary_block}\n\n"
        f"---"
    )


def generate_report(
    entries: list[ReportEntry],
    title: str = "Threat Hunting Report",
) -> str:
    """Generate a Markdown threat hunting report from a list of ReportEntries.

    Each entry is rendered as a numbered section containing the SQL query,
    a results table, and a fact-based summary. The summary lists only observed
    facts (counts, top values) without speculative threat assessments.
    Sensitive credential-like strings are automatically redacted throughout.

    Args:
        entries: Ordered list of query-result-summary triples.
        title:   Report title shown in the top-level heading.

    Returns:
        A complete Markdown document as a string.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    header = f"# {title}\n\n**Generated:** {timestamp}\n\n---\n"
    sections = [_render_entry(i + 1, entry) for i, entry in enumerate(entries)]

    return "\n\n".join([header] + sections) + "\n"
