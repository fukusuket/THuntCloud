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


def _render_toc_html(entries: list[ReportEntry]) -> str:
    """Render the table of contents as an HTML ``<nav>`` element.

    Args:
        entries: Ordered list of ReportEntry objects.

    Returns:
        HTML string for the sticky left-sidebar navigation.
    """
    items = []
    for i, entry in enumerate(entries, 1):
        heading_text = _build_heading(i, entry)
        anchor = _heading_anchor(heading_text)
        # Use a shorter label for the sidebar (label only, no count badge)
        count = _result_count(entry)
        badge_cls = "badge-ok" if count > 0 else "badge-empty"
        short_label = entry.label if entry.label else f"Query {i}"
        category_span = (
            f'<span class="toc-cat">{entry.category}</span>' if entry.category else ""
        )
        items.append(
            f"<li>"
            f'<a href="#{anchor}">'
            f'<span class="toc-num">{i}.</span> '
            f"{category_span}"
            f'<span class="toc-label">{short_label}</span>'
            f'<span class="badge {badge_cls}">{count:,}</span>'
            f"</a>"
            f"</li>"
        )
    items_html = "\n".join(items)
    return f"""<nav id="toc">
  <div class="toc-title">📋 Contents</div>
  <ol>{items_html}</ol>
</nav>"""


def _render_entry_html(index: int, entry: ReportEntry) -> str:
    """Render one ReportEntry as an HTML ``<section>`` block.

    Args:
        index: 1-based query number.
        entry: The ReportEntry to render.

    Returns:
        HTML string for the section.
    """
    heading_text = _build_heading(index, entry)
    anchor = _heading_anchor(heading_text)

    # Results table
    if entry.results is not None and not entry.results.empty:
        results_html = entry.results.head(1000).to_html(index=False, border=0)
        results_html = f'<div class="table-wrap">{results_html}</div>'
    else:
        results_html = '<p class="no-results">No results returned.</p>'

    sql_block = _sanitize(entry.sql)
    results_html_sanitized = _sanitize(results_html)
    summary_block = (
        f"<p>{_sanitize(entry.analysis)}</p>"
        if entry.analysis
        else '<p class="no-results">(no summary)</p>'
    )

    analyst_section = ""
    if entry.analyst_note:
        note = _sanitize(entry.analyst_note)
        analyst_section = (
            f'<h3>📝 Analyst Note</h3><div class="analyst-note">{note}</div>'
        )

    category_badge = (
        f'<span class="cat-badge">{entry.category}</span>' if entry.category else ""
    )

    return f"""<section id="{anchor}">
  <h2>{category_badge}{heading_text}</h2>
  <h3>SQL</h3>
  <pre><code class="language-sql">{sql_block}</code></pre>
  <h3>Results</h3>
  {results_html_sanitized}
  <h3>Summary</h3>
  {summary_block}
  {analyst_section}
</section>
<hr>"""


def generate_html_report(
    entries: list[ReportEntry],
    title: str = "Threat Hunting Report",
) -> str:
    """Generate a self-contained HTML threat hunting report with sidebar TOC.

    Renders a two-column layout: a fixed left sidebar showing the table of
    contents with per-query result counts, and a scrollable right panel
    containing the full query details.  Light color scheme.

    Args:
        entries: Ordered list of query-result-summary triples.
        title:   Report title shown in the page title and top heading.

    Returns:
        A complete self-contained HTML document as a string.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    sidebar_w = "420px"

    toc_html = _render_toc_html(entries)
    sections_html = "\n".join(
        _render_entry_html(i + 1, entry) for i, entry in enumerate(entries)
    )

    css = f"""
/* ── Reset / Base ───────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f5f7fa;
    color: #1a1a2e;
    line-height: 1.7;
    font-size: 14px;
}}

/* ── Header ─────────────────────────────── */
header {{
    background: #1e3a5f;
    border-bottom: 2px solid #1565c0;
    padding: .75rem 1.5rem;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 54px;
    z-index: 200;
    display: flex;
    align-items: center;
    gap: 1rem;
}}
header h1 {{ color: #ffffff; font-size: 1.1rem; white-space: nowrap; }}
header .meta {{ color: #90caf9; font-size: .78rem; }}

/* ── TOC sidebar ─────────────────────────── */
#toc {{
    width: {sidebar_w};
    background: #ffffff;
    border-right: 1px solid #dde3ec;
    position: fixed;
    top: 54px;
    left: 0;
    bottom: 0;
    overflow-y: auto;
    padding: 1rem .75rem 2rem;
    z-index: 100;
    box-shadow: 2px 0 6px rgba(0,0,0,.06);
}}
#toc::-webkit-scrollbar {{ width: 5px; }}
#toc::-webkit-scrollbar-thumb {{ background: #b0bec5; border-radius: 3px; }}
.toc-title {{
    color: #1565c0;
    font-size: .75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .07em;
    margin-bottom: .6rem;
    padding-bottom: .4rem;
    border-bottom: 2px solid #e3eaf4;
}}
#toc ol {{ list-style: none; padding: 0; }}
#toc li {{ margin: .15rem 0; }}
#toc a {{
    display: flex;
    align-items: baseline;
    gap: .3rem;
    color: #37474f;
    text-decoration: none;
    font-size: .8rem;
    padding: .28rem .5rem;
    border-radius: 5px;
    flex-wrap: wrap;
    transition: background .12s, color .12s;
}}
#toc a:hover {{ background: #e8f0fe; color: #1565c0; }}
.toc-num {{ color: #90a4ae; font-size: .72rem; flex-shrink: 0; }}
.toc-cat {{ color: #78909c; font-size: .72rem; }}
.toc-label {{ flex: 1; min-width: 0; word-break: break-word; }}
.badge {{
    font-size: .68rem;
    padding: .1em .5em;
    border-radius: 10px;
    flex-shrink: 0;
    font-weight: 700;
}}
.badge-ok    {{ background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }}
.badge-empty {{ background: #f5f5f5; color: #9e9e9e; border: 1px solid #e0e0e0; }}

/* ── Main content ────────────────────────── */
main {{
    margin-left: {sidebar_w};
    margin-top: 54px;
    padding: 2rem 3rem 4rem;
}}

/* ── Sections ────────────────────────────── */
section {{ margin-bottom: 2rem; }}
h2 {{
    color: #1565c0;
    font-size: 1.05rem;
    border-bottom: 2px solid #e3eaf4;
    padding-bottom: .35rem;
    margin: 2.2rem 0 .8rem;
    scroll-margin-top: 70px;
}}
h3 {{
    color: #37474f;
    font-size: .9rem;
    font-weight: 600;
    margin: 1.2rem 0 .4rem;
    text-transform: uppercase;
    letter-spacing: .05em;
}}
.cat-badge {{
    display: inline-block;
    background: #e8f0fe;
    color: #1565c0;
    font-size: .68rem;
    padding: .1em .5em;
    border-radius: 4px;
    margin-right: .5rem;
    vertical-align: middle;
    font-weight: 600;
    border: 1px solid #bbdefb;
}}

/* ── Code ────────────────────────────────── */
pre {{
    background: #f8f9fb;
    border: 1px solid #dde3ec;
    border-left: 3px solid #1565c0;
    border-radius: 0 6px 6px 0;
    padding: 1rem 1.2rem;
    overflow-x: auto;
    font-size: .83rem;
    margin: .5rem 0;
}}
code {{ font-family: "Fira Code", "Cascadia Code", Consolas, monospace; }}

/* ── Tables ──────────────────────────────── */
.table-wrap {{ overflow-x: auto; margin: .5rem 0; border-radius: 6px; border: 1px solid #dde3ec; }}
table {{ border-collapse: collapse; width: 100%; font-size: .8rem; }}
th {{
    background: #e8f0fe;
    color: #1a237e;
    border-bottom: 2px solid #bbdefb;
    border-right: 1px solid #dde3ec;
    padding: .45rem .75rem;
    text-align: left;
    white-space: nowrap;
    font-weight: 600;
}}
td {{ border-bottom: 1px solid #eceff1; border-right: 1px solid #eceff1; padding: .4rem .75rem; word-break: break-word; }}
tr:last-child td {{ border-bottom: none; }}
tr:nth-child(even) td {{ background: #f8f9fb; }}

/* ── Misc ────────────────────────────────── */
hr {{ border: none; border-top: 1px solid #e0e7ef; margin: 2rem 0; }}
.no-results {{ color: #9e9e9e; font-style: italic; }}
.analyst-note {{
    background: #fffde7;
    border-left: 3px solid #f9a825;
    padding: .75rem 1rem;
    border-radius: 0 6px 6px 0;
    font-size: .88rem;
    white-space: pre-wrap;
    color: #4e342e;
}}
a {{ color: #1565c0; }}
a:hover {{ text-decoration: underline; }}
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
<header>
  <h1>🔍 {title}</h1>
  <span class="meta">Generated: {timestamp} &nbsp;·&nbsp; {len(entries)} queries</span>
</header>
{toc_html}
<main>
  {sections_html}
</main>
</body>
</html>
"""
