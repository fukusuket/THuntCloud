"""import_dashboard.py — Import the pre-built CloudTrail dashboard into Superset.

Uses the Superset Python API (ImportDashboardsCommand) instead of the CLI,
because the CLI requires a --username flag and does not work well in
non-interactive bootstrap scripts.

This script runs inside the superset-init container as part of bootstrap.sh.
"""

import os
import sys
import zipfile

DASHBOARD_ZIP = os.environ.get(
    "DASHBOARD_ZIP", "/app/dashboards/cloudtrail_default.zip"
)
ADMIN_USERNAME = os.environ.get("SUPERSET_ADMIN_USERNAME", "admin")


def main() -> None:
    """Import the dashboard ZIP using the Superset Python API."""
    if not os.path.exists(DASHBOARD_ZIP):
        print(f"    Dashboard ZIP not found at {DASHBOARD_ZIP} — skipping.")
        sys.exit(0)

    # Step 1: create the Flask app (no model imports yet).
    from superset import create_app, security_manager  # noqa: PLC0415

    app = create_app()
    app_ctx = app.app_context()
    app_ctx.push()

    # Step 2: push a request context and set g.user so permission checks pass.
    req_ctx = app.test_request_context()
    req_ctx.push()

    from flask import g  # noqa: PLC0415

    admin = security_manager.find_user(ADMIN_USERNAME)
    if admin is None:
        print(f"    User '{ADMIN_USERNAME}' not found — aborting import.")
        sys.exit(1)
    g.user = admin

    # Step 3: load ZIP and run import command.
    from superset.commands.dashboard.importers.dispatcher import (  # noqa: PLC0415
        ImportDashboardsCommand,
    )

    with zipfile.ZipFile(DASHBOARD_ZIP) as z:
        contents = {name: z.read(name) for name in z.namelist()}

    try:
        ImportDashboardsCommand(contents, overwrite=True).run()
        print("    Dashboard imported successfully.")
    except Exception as exc:  # noqa: BLE001
        print(f"    Dashboard import failed: {exc}")
        import traceback  # noqa: PLC0415

        traceback.print_exc()
        sys.exit(1)
    finally:
        req_ctx.pop()
        app_ctx.pop()


if __name__ == "__main__":
    main()

