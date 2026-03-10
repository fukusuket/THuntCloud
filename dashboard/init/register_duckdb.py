"""register_duckdb.py — Register the DuckDB database connection in Superset.

This script runs inside the superset-init container as part of bootstrap.sh.
It uses Superset's internal Python API to create the CloudTrail DuckDB
connection idempotently (safe to run multiple times).

Superset 4.x removed the `set_database_uri` CLI command, so this Python
approach is the supported replacement.

Implementation note:
    superset.models.core (and helpers) access `app.config` at import time via
    Werkzeug's LocalProxy.  We must therefore push the application context
    BEFORE importing those modules.  The pattern is:
        1. Import only `create_app` (no model imports yet).
        2. Build the app and push its context.
        3. Import models inside the pushed context.
"""

import os
import sys

DB_NAME = "CloudTrail DuckDB"
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "/data/db/threat_hunting.db")
# Four slashes: duckdb:// (scheme) + empty host + /absolute/path
# read_only=true prevents any write operations through Superset.
SQLALCHEMY_URI = f"duckdb:////{DUCKDB_PATH}?read_only=true"


def main() -> None:
    """Register the DuckDB database connection if it does not already exist."""
    # Step 1 — create the Flask app (no model imports yet).
    from superset import create_app  # noqa: PLC0415

    app = create_app()

    # Step 2 — push the context so Werkzeug LocalProxy resolves `current_app`.
    ctx = app.app_context()
    ctx.push()

    try:
        # Step 3 — now it is safe to import models that access app.config.
        from superset.extensions import db  # noqa: PLC0415
        from superset.models.core import Database  # noqa: PLC0415

        existing = (
            db.session.query(Database).filter_by(database_name=DB_NAME).first()
        )
        if existing:
            print(f"    Database '{DB_NAME}' already registered — skipping.")
            return

        database = Database(
            database_name=DB_NAME,
            sqlalchemy_uri=SQLALCHEMY_URI,
            expose_in_sqllab=True,
            allow_run_async=True,
            allow_ctas=False,
            allow_cvas=False,
            allow_dml=False,
        )
        db.session.add(database)
        db.session.commit()
        print(f"    Database '{DB_NAME}' registered successfully.")
        print(f"    URI: {SQLALCHEMY_URI}")
    finally:
        ctx.pop()


if __name__ == "__main__":
    main()
    sys.exit(0)
