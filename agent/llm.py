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

from prompts.system_prompt import SYSTEM_PROMPT
from schema import get_schema_description

logger = logging.getLogger(__name__)


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
    """Instantiate an OpenAI client with the given API key.

    When running behind a corporate proxy that performs TLS inspection,
    set the ``SSL_CERT_FILE`` or ``REQUESTS_CA_BUNDLE`` environment
    variable to point to a CA bundle that includes the proxy's root CA.
    This function forwards that bundle to the underlying *httpx* client
    so that certificate verification succeeds.
    """
    ca_bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get(
        "REQUESTS_CA_BUNDLE"
    )
    if ca_bundle:
        http_client = httpx.Client(verify=ca_bundle)
        return OpenAI(api_key=api_key, http_client=http_client)
    return OpenAI(api_key=api_key)


def generate_sql(
    user_query: str,
    api_key: str,
    model: str = "gpt-5.4",
) -> str:
    """Generate a DuckDB SQL query from a natural language question.

    Args:
        user_query: The natural language threat hunting question.
        api_key:    OpenAI API key.
        model:      Model name to use for generation (default: gpt-5.4).

    Returns:
        A DuckDB SQL string. On API error, returns a user-friendly error message.
    """
    client = _create_client(api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        return _strip_markdown_fences(raw)
    except OpenAIError as exc:
        logger.exception("OpenAI API error during SQL generation")
        return f"[error] OpenAI API error: {exc}"


def generate_analysis(
    sql: str,
    results: pd.DataFrame,
    api_key: str,
    model: str = "gpt-5.4",
) -> str:
    """Generate Markdown analysis text for SQL query results.

    Serialises up to 50 rows of the DataFrame as a Markdown table and asks
    the LLM to provide a threat hunting analysis.

    Args:
        sql:     The SQL query that produced the results.
        results: The query result as a pandas DataFrame.
        api_key: OpenAI API key.
        model:   Model name to use (default: gpt-5.4).

    Returns:
        Markdown-formatted analysis text. On API error, returns a user-friendly
        error message.
    """
    sample = (
        results.head(50).to_markdown(index=False)
        if not results.empty
        else "(no results)"
    )
    user_message = (
        f"The following SQL query was executed against AWS CloudTrail logs:\n\n"
        f"```sql\n{sql}\n```\n\n"
        f"Results (up to 50 rows):\n\n{sample}\n\n"
        f"Please provide a concise threat hunting analysis in Markdown."
    )
    client = _create_client(api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""
    except OpenAIError as exc:
        logger.exception("OpenAI API error during analysis generation")
        return f"[error] OpenAI API error: {exc}"
