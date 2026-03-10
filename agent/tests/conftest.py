"""Shared pytest fixtures for the agent test suite."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client that returns a predefined SQL response."""
    with patch("llm.OpenAI") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = (
            "SELECT event_name, COUNT(*) as cnt "
            "FROM cloudtrail_events "
            "GROUP BY event_name ORDER BY cnt DESC LIMIT 10"
        )
        client.chat.completions.create.return_value = response

        yield client


@pytest.fixture
def tmp_duckdb(tmp_path):
    """Create a temporary DuckDB with cloudtrail_events table and sample rows."""
    import duckdb

    db_path = tmp_path / "test.db"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE cloudtrail_events (
            event_time               TIMESTAMP,
            event_name               VARCHAR,
            event_source             VARCHAR,
            aws_region               VARCHAR,
            source_ip_address        VARCHAR,
            user_agent               VARCHAR,
            user_identity_type       VARCHAR,
            user_identity_arn        VARCHAR,
            user_identity_account_id VARCHAR,
            request_parameters       JSON,
            response_elements        JSON,
            error_code               VARCHAR,
            error_message            VARCHAR,
            read_only                BOOLEAN,
            event_type               VARCHAR,
            recipient_account_id     VARCHAR,
            raw_event                JSON
        )
    """)
    conn.execute("""
        INSERT INTO cloudtrail_events (event_time, event_name, event_source, aws_region)
        VALUES
            ('2024-01-15 10:30:00', 'DescribeInstances', 'ec2.amazonaws.com', 'us-east-1'),
            ('2024-01-15 10:31:00', 'DescribeInstances', 'ec2.amazonaws.com', 'us-east-1'),
            ('2024-01-15 10:32:00', 'CreateUser',        'iam.amazonaws.com', 'us-east-1')
    """)
    conn.close()
    yield str(db_path)
