"""register_dataset.py — Register the cloudtrail_events dataset in Superset.

This script runs inside the superset-init container as part of bootstrap.sh.
It creates a Superset SqlaTable (dataset) for cloudtrail_events, linked to
the "CloudTrail DuckDB" database connection registered by register_duckdb.py.

The registration is idempotent: running this script multiple times is safe.

Implementation note:
    Same context-push pattern as register_duckdb.py — superset model imports
    must happen AFTER app context is pushed to avoid Werkzeug LocalProxy errors.
"""

import os
import sys

DB_NAME = "CloudTrail DuckDB"
TABLE_NAME = "cloudtrail_events"
MAIN_DTTM_COL = "event_time"
DESCRIPTION = "AWS CloudTrail events ingested by the THuntCloud ingester (Rust)."
# Fixed UUID — must match datasets/CloudTrail_DuckDB/cloudtrail_events.yaml in the ZIP
DATASET_UUID = "d8444b4a-ac55-4710-a777-a5b940bebabe"


def main() -> None:
    """Register the cloudtrail_events dataset if it does not already exist."""
    # Step 1 — create Flask app without importing models yet.
    from superset import create_app  # noqa: PLC0415

    app = create_app()

    # Step 2 — push context so Werkzeug LocalProxy resolves current_app.
    ctx = app.app_context()
    ctx.push()

    try:
        # Step 3 — safe to import models now.
        from superset.connectors.sqla.models import SqlaTable  # noqa: PLC0415
        from superset.extensions import db  # noqa: PLC0415
        from superset.models.core import Database  # noqa: PLC0415

        # Look up the target database connection.
        database = (
            db.session.query(Database).filter_by(database_name=DB_NAME).first()
        )
        if not database:
            print(f"    ERROR: Database '{DB_NAME}' not found.")
            print("    Run register_duckdb.py first.")
            sys.exit(1)

        # Check if the dataset already exists.
        existing = (
            db.session.query(SqlaTable)
            .filter_by(table_name=TABLE_NAME, database_id=database.id)
            .first()
        )
        if existing:
            print(f"    Dataset '{TABLE_NAME}' already registered — skipping.")
            return

        # Create the dataset with a fixed UUID so the dashboard ZIP can reference it.
        import uuid as _uuid  # noqa: PLC0415
        dataset = SqlaTable(
            table_name=TABLE_NAME,
            database_id=database.id,
            main_dttm_col=MAIN_DTTM_COL,
            description=DESCRIPTION,
            filter_select_enabled=True,
            uuid=_uuid.UUID(DATASET_UUID),
        )
        db.session.add(dataset)
        db.session.commit()

        # Attempt to fetch column metadata from DuckDB.
        # This may fail if the DB file is empty or not yet populated by the ingester.
        # Superset will re-sync columns automatically on first SQL Lab access.
        try:
            dataset.fetch_metadata()
            db.session.commit()
            print(f"    Column metadata synced from '{TABLE_NAME}'.")
        except Exception as exc:  # noqa: BLE001
            print(f"    Warning: could not sync column metadata: {exc}")
            print("    Columns will be auto-synced on first SQL Lab access.")

        print(f"    Dataset '{TABLE_NAME}' registered successfully.")
        print(f"    Linked to database: '{DB_NAME}' (id={database.id})")

        # Register custom metrics required by dashboard charts.
        _register_metrics(dataset)
    finally:
        ctx.pop()


# Custom metrics used by the pre-built dashboard charts.
CUSTOM_METRICS = [
    ("event_count", "COUNT(*)", "Total event count"),
    ("call_count", "COUNT(*)", "API call count"),
    ("total_events", "COUNT(*)", "Total events per entity"),
    ("write_events", "COUNT(CASE WHEN read_only = false THEN 1 END)", "Write (mutating) events"),
    ("error_events", "COUNT(CASE WHEN error_code IS NOT NULL THEN 1 END)", "Events with error code"),
    ("error_count", "COUNT(CASE WHEN error_code IS NOT NULL THEN 1 END)", "Error event count"),
    ("request_count", "COUNT(*)", "Request count per source IP"),
    ("unique_identities", "COUNT(DISTINCT user_identity_arn)", "Unique IAM identities"),
    ("write_requests", "COUNT(CASE WHEN read_only = false THEN 1 END)", "Write requests per source IP"),
]


def _register_metrics(dataset: "SqlaTable") -> None:
    """Add custom metrics to the dataset if they do not already exist."""
    from superset.connectors.sqla.models import SqlMetric  # noqa: PLC0415
    from superset.extensions import db  # noqa: PLC0415

    existing_names = {m.metric_name for m in dataset.metrics}
    added = 0
    for name, expression, description in CUSTOM_METRICS:
        if name in existing_names:
            continue
        metric = SqlMetric(
            metric_name=name,
            expression=expression,
            description=description,
            metric_type="count",
            table_id=dataset.id,
        )
        db.session.add(metric)
        added += 1

    if added:
        db.session.commit()
        print(f"    Registered {added} custom metrics.")
    else:
        print("    Custom metrics already registered — skipping.")


if __name__ == "__main__":
    main()
    sys.exit(0)


