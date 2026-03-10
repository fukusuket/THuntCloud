"""Tests for llm.py — OpenAI API integration for SQL generation and analysis."""

import openai
import pandas as pd

from llm import build_system_prompt, generate_analysis, generate_sql


def test_build_system_prompt_includes_schema():
    """The system prompt includes the CloudTrail table schema."""
    prompt = build_system_prompt()

    assert "cloudtrail_events" in prompt
    assert "event_time" in prompt
    assert "event_name" in prompt


def test_build_system_prompt_includes_duckdb_dialect():
    """The system prompt specifies DuckDB SQL dialect."""
    prompt = build_system_prompt()

    assert "DuckDB" in prompt


def test_generate_sql_returns_sql_string(mock_openai_client):
    """Given a mocked OpenAI response, generate_sql() returns a SQL string."""
    sql = generate_sql("Show me all CreateUser events", api_key="sk-test")

    assert isinstance(sql, str)
    assert "SELECT" in sql.upper()
    assert "cloudtrail_events" in sql


def test_generate_sql_strips_markdown_fences(mock_openai_client):
    """If the LLM wraps SQL in ```sql ... ```, the fences are stripped."""
    mock_openai_client.chat.completions.create.return_value.choices[
        0
    ].message.content = "```sql\nSELECT event_name FROM cloudtrail_events LIMIT 10\n```"

    sql = generate_sql("List events", api_key="sk-test")

    assert not sql.startswith("```")
    assert not sql.endswith("```")
    assert "SELECT" in sql.upper()


def test_generate_analysis_returns_markdown(mock_openai_client):
    """Given query results, generate_analysis() returns Markdown analysis text."""
    mock_openai_client.chat.completions.create.return_value.choices[
        0
    ].message.content = "## Analysis\n\nFound 3 events."

    df = pd.DataFrame(
        {
            "event_name": ["DescribeInstances", "DescribeInstances", "CreateUser"],
            "cnt": [2, 2, 1],
        }
    )
    result = generate_analysis(
        sql="SELECT event_name, COUNT(*) as cnt FROM cloudtrail_events GROUP BY event_name",
        results=df,
        api_key="sk-test",
    )

    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_sql_handles_api_error(mock_openai_client):
    """OpenAI API errors are caught and surfaced as user-friendly messages."""
    mock_openai_client.chat.completions.create.side_effect = openai.OpenAIError(
        "connection error"
    )

    result = generate_sql("Show me all events", api_key="sk-test")

    assert isinstance(result, str)
    assert "error" in result.lower()
