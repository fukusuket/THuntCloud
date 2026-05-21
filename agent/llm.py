"""OpenAI API integration for SQL generation and result analysis.

Generates DuckDB SQL from natural language queries and produces
Markdown analysis of query results using the OpenAI chat API.
"""

import logging
import os
import re

import httpx
import pandas as pd
from openai import OpenAI, OpenAIError

from prompts.analysis_prompt import ANALYSIS_SYSTEM_PROMPT, ANALYSIS_USER_TEMPLATE
from prompts.system_prompt import SYSTEM_PROMPT
from schema import get_schema_description

logger = logging.getLogger(__name__)

# Maximum number of prior conversation turns to inject into the SQL generation prompt.
MAX_CONTEXT_TURNS: int = 5

# Module-level OpenAI client cache keyed by api_key.
# Avoids creating a new httpx connection pool on every LLM call within a
# single Streamlit request (generate_sql → fix_sql_with_llm → generate_analysis).
_client_cache: dict[str, OpenAI] = {}


def _clear_client_cache() -> None:
    """Clear the module-level OpenAI client cache.

    Intended for use in tests only.  Calling this between tests prevents a
    cached mock client from leaking into subsequent test cases.
    """
    _client_cache.clear()


def build_system_prompt() -> str:
    """Build the system prompt including the CloudTrail schema description.

    Returns:
        A formatted system prompt string that instructs the LLM to generate
        DuckDB-compatible SQL for the cloudtrail_events table.
    """
    return SYSTEM_PROMPT.format(schema=get_schema_description())


def _strip_markdown_fences(text: str) -> str:
    """Remove ```sql ... ``` or ``` ... ``` wrappers from LLM output.

    Args:
        text: Raw text returned by the LLM.

    Returns:
        The text with Markdown code fences removed.
    """
    text = re.sub(r"^```(?:sql)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    return text.strip()


def _create_client(api_key: str) -> OpenAI:
    """Return a cached OpenAI client for *api_key*, creating one if necessary.

    Caching avoids opening a new httpx connection pool on every LLM call.
    The cache is keyed solely on *api_key*; the CA bundle (if any) is baked
    in at first-creation time and stable for the lifetime of the process.

    When running behind a corporate proxy that performs TLS inspection,
    set the ``SSL_CERT_FILE`` or ``REQUESTS_CA_BUNDLE`` environment
    variable to point to a CA bundle that includes the proxy's root CA.
    """
    if api_key not in _client_cache:
        ca_bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get(
            "REQUESTS_CA_BUNDLE"
        )
        if ca_bundle:
            http_client = httpx.Client(verify=False)
            _client_cache[api_key] = OpenAI(api_key=api_key, http_client=http_client)
        else:
            _client_cache[api_key] = OpenAI(api_key=api_key)
    return _client_cache[api_key]


def _build_context_messages(context: list[dict], max_turns: int) -> list[dict]:
    """Convert conversation context entries to OpenAI message pairs.

    Takes the most recent *max_turns* entries from *context* and formats
    each as a user/assistant message pair so the LLM understands prior
    exchanges when generating the next SQL query.

    Args:
        context:   List of dicts with 'user_query', 'sql', and 'summary' keys.
        max_turns: Maximum number of prior turns to include.

    Returns:
        A flat list of OpenAI message dicts (role + content), alternating
        user and assistant entries.
    """
    recent = context[-max_turns:] if len(context) > max_turns else context
    messages: list[dict] = []
    for turn in recent:
        messages.append({"role": "user", "content": turn.get("user_query", "")})
        sql_text = turn.get("sql", "")
        summary_text = turn.get("summary", "(no summary)") or "(no summary)"
        messages.append(
            {
                "role": "assistant",
                "content": f"```sql\n{sql_text}\n```\n\n{summary_text}",
            }
        )
    return messages


def generate_sql(
    user_query: str,
    api_key: str,
    model: str = "gpt-5.5",
    context: list[dict] | None = None,
) -> str:
    """Generate a DuckDB SQL query from a natural language question.

    Args:
        user_query: The natural language threat hunting question.
        api_key:    OpenAI API key.
        model:      Model name to use for generation (default: gpt-5.5).
        context:    Optional list of prior conversation turns. Each entry
                    must contain 'user_query', 'sql', and 'summary' keys.
                    When provided, the most recent MAX_CONTEXT_TURNS entries
                    are injected as user/assistant message pairs before the
                    current query, enabling follow-up questions.

    Returns:
        A DuckDB SQL string. On API error, returns a user-friendly error message.
    """
    client = _create_client(api_key)
    try:
        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt()},
        ]
        if context:
            messages.extend(_build_context_messages(context, MAX_CONTEXT_TURNS))
        messages.append({"role": "user", "content": user_query})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        return _strip_markdown_fences(raw)
    except OpenAIError as exc:
        logger.exception("OpenAI API error during SQL generation")
        return f"[error] OpenAI API error: {exc}"


def fix_sql_with_llm(
    broken_sql: str,
    error_message: str,
    api_key: str,
    model: str = "gpt-5.5",
) -> str:
    """Attempt to fix a SQL query that failed validation using the LLM.

    Sends the broken SQL along with the validation error message to the LLM
    and asks it to return a corrected DuckDB-compatible SQL string.

    Args:
        broken_sql:    The SQL query that failed validation.
        error_message: The error message produced by the validation failure.
        api_key:       OpenAI API key.
        model:         Model name to use (default: gpt-5.5).

    Returns:
        A corrected DuckDB SQL string. On API error, returns a string
        starting with '[error]'.
    """
    client = _create_client(api_key)
    user_message = (
        f"The following SQL query failed validation:\n\n"
        f"```sql\n{broken_sql}\n```\n\n"
        f"Error: {error_message}\n\n"
        f"Please fix the SQL so it is valid DuckDB SQL for the cloudtrail_events table. "
        f"Return only the corrected SQL, with no explanation."
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        return _strip_markdown_fences(raw)
    except OpenAIError as exc:
        logger.exception("OpenAI API error during SQL fix")
        return f"[error] OpenAI API error: {exc}"


def generate_analysis(
    sql: str,
    results: pd.DataFrame,
    api_key: str,
    model: str = "gpt-5.5",
) -> str:
    """Generate a fact-based summary for SQL query results.

    Serialises up to 50 rows of the DataFrame as a Markdown table and asks
    the LLM to list only observed facts — counts, top values, and anomalies
    present in the data. Speculative threat assessments are explicitly excluded.

    Args:
        sql:     The SQL query that produced the results.
        results: The query result as a pandas DataFrame.
        api_key: OpenAI API key.
        model:   Model name to use (default: gpt-5.5).

    Returns:
        Markdown bullet-point summary. On API error, returns a user-friendly
        error message.
    """
    sample = (
        results.head(50).to_markdown(index=False)
        if not results.empty
        else "(no results)"
    )
    user_message = ANALYSIS_USER_TEMPLATE.format(sql=sql, results=sample)
    client = _create_client(api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""
    except OpenAIError as exc:
        logger.exception("OpenAI API error during summary generation")
        return f"[error] OpenAI API error: {exc}"
