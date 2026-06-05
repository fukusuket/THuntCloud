"""Threat hunting report generation.

Generates structured Markdown reports from investigation sessions,
including queries, results, analysis, and sensitive data redaction.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
import markdown as md_lib

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
    description: str = ""
    chart_config: dict | None = None
    analyst_note: str = ""  # UI-01: freeform Markdown note by the analyst
    label: str = ""  # UI-02: display name (e.g. "🔑 Root Account Activity")
    category: str = ""  # UI-02: category group (e.g. "🔑 Identity & Access")
    source: str = "chat"  # UI-03: "chat" | "bulk"
    # Prevent pandas DataFrame equality issues in dataclass comparisons
    _results_placeholder: None = field(default=None, init=False, repr=False)


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------


def _result_count(entry: ReportEntry) -> int:
    """Return the number of rows in the entry's result DataFrame (0 if empty).

    Args:
        entry: The ReportEntry to inspect.

    Returns:
        Row count as an integer.
    """
    if entry.results is not None and not entry.results.empty:
        return len(entry.results)
    return 0


def _build_heading(index: int, entry: ReportEntry) -> str:
    """Build the ``##`` level heading text including result count badge.

    Args:
        index: 1-based query number.
        entry: The ReportEntry whose label/category/row count are used.

    Returns:
        Heading string without the leading ``## `` prefix.
    """
    count = _result_count(entry)
    count_badge = f"({count:,} rows)"

    if entry.label:
        if entry.category:
            return f"Query {index} — {entry.category}  ›  {entry.label}  {count_badge}"
        return f"Query {index} — {entry.label}  {count_badge}"
    return f"Query {index}  {count_badge}"


def _heading_anchor(heading_text: str) -> str:
    """Convert a heading text to a GitHub-flavored Markdown anchor fragment.

    Lowercases the text, replaces spaces with hyphens, and strips characters
    that are not alphanumeric, hyphens, or underscores.

    Args:
        heading_text: Plain heading text (without ``##`` prefix).

    Returns:
        Anchor fragment string (without leading ``#``).
    """
    anchor = heading_text.lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    anchor = re.sub(r"\s+", "-", anchor.strip())
    return anchor


def _render_toc(entries: list[ReportEntry]) -> str:
    """Render a Markdown table of contents for all report entries.

    Each line is a numbered list item linking to the corresponding section
    anchor, including the result count.

    Args:
        entries: Ordered list of ReportEntry objects.

    Returns:
        A Markdown string containing the TOC block.
    """
    lines = ["## Table of Contents", ""]
    for i, entry in enumerate(entries, 1):
        heading_text = _build_heading(i, entry)
        anchor = _heading_anchor(heading_text)
        lines.append(f"{i}. [{heading_text}](#{anchor})")
    return "\n".join(lines)


def _render_entry(index: int, entry: ReportEntry) -> str:
    """Render one ReportEntry as a Markdown section.

    Outputs the SQL query, results table, and a fact-based summary.
    When label and/or category are set they appear prominently in the heading.
    Result count is appended to the heading.
    When analyst_note is non-empty it is included under its own heading.
    Sensitive credential-like strings are automatically redacted throughout.

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

    heading = f"## {_build_heading(index, entry)}"

    # Analyst note section (only when non-empty)
    analyst_note_section = ""
    if entry.analyst_note:
        analyst_note_block = _sanitize(entry.analyst_note)
        analyst_note_section = f"\n### Analyst Note\n\n{analyst_note_block}\n"

    return (
        f"{heading}\n\n"
        f"### SQL\n\n"
        f"```sql\n{sql_block}\n```\n\n"
        f"### Results\n\n"
        f"{results_block}\n\n"
        f"### Summary\n\n"
        f"{summary_block}\n"
        f"{analyst_note_section}"
        f"\n---"
    )


def generate_report(
    entries: list[ReportEntry],
    title: str = "Threat Hunting Report",
) -> str:
    """Generate a Markdown threat hunting report from a list of ReportEntries.

    Each entry is rendered as a numbered section containing the SQL query,
    a results table, and a fact-based summary. A table of contents with
    result counts is inserted after the header. The summary lists only
    observed facts (counts, top values) without speculative threat assessments.
    Sensitive credential-like strings are automatically redacted throughout.

    Args:
        entries: Ordered list of query-result-summary triples.
        title:   Report title shown in the top-level heading.

    Returns:
        A complete Markdown document as a string.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    header = f"# {title}\n\n**Generated:** {timestamp}\n\n---\n"
    toc = _render_toc(entries)
    sections = [_render_entry(i + 1, entry) for i, entry in enumerate(entries)]

    return "\n\n".join([header, toc, "---"] + sections) + "\n"


def generate_html_report(
    entries: list[ReportEntry],
    title: str = "Threat Hunting Report",
) -> str:
    """Generate a self-contained HTML threat hunting report.

    Converts the Markdown report to HTML and wraps it in a styled HTML
    document with a dark-themed CSS suitable for security analysis.
    Tables, code blocks, and anchor links in the table of contents are
    all rendered correctly.

    Args:
        entries: Ordered list of query-result-summary triples.
        title:   Report title shown in the page title and top heading.

    Returns:
        A complete HTML document as a string.
    """
    md_text = generate_report(entries, title=title)

    body_html = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )

    css = """
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: #0f1117;
        color: #e0e0e0;
        max-width: 1100px;
        margin: 0 auto;
        padding: 2rem 1.5rem;
        line-height: 1.7;
    }
    h1 { color: #4fc3f7; border-bottom: 2px solid #4fc3f7; padding-bottom: .4rem; }
    h2 { color: #81d4fa; border-bottom: 1px solid #37474f; padding-bottom: .3rem; margin-top: 2.5rem; }
    h3 { color: #b0bec5; }
    a { color: #4fc3f7; text-decoration: none; }
    a:hover { text-decoration: underline; }
    hr { border: none; border-top: 1px solid #37474f; margin: 2rem 0; }
    pre {
        background: #1e2330;
        border: 1px solid #37474f;
        border-radius: 6px;
        padding: 1rem;
        overflow-x: auto;
        font-size: .875rem;
    }
    code {
        background: #1e2330;
        border-radius: 3px;
        padding: .15em .4em;
        font-size: .9em;
    }
    pre code { background: transparent; padding: 0; }
    table {
        border-collapse: collapse;
        width: 100%;
        font-size: .875rem;
        margin: 1rem 0;
    }
    th {
        background: #1e2330;
        color: #81d4fa;
        border: 1px solid #37474f;
        padding: .5rem .75rem;
        text-align: left;
    }
    td {
        border: 1px solid #37474f;
        padding: .45rem .75rem;
    }
    tr:nth-child(even) td { background: #161b25; }
    .toc { background: #1e2330; border: 1px solid #37474f; border-radius: 6px; padding: 1rem 1.5rem; margin: 1.5rem 0; }
    .toc ol { margin: .4rem 0 0; padding-left: 1.4rem; }
    .toc li { margin: .25rem 0; }
    blockquote { border-left: 4px solid #37474f; margin: 0; padding-left: 1rem; color: #90a4ae; }
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
{body_html}
</body>
</html>
"""
