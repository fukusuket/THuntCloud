"""Superset configuration overrides for THuntCloud.

This file is mounted into the Superset container at
/app/pythonpath/superset_config.py and is loaded automatically by Superset.
"""

import os

# Secret key for session signing — MUST be overridden in production via env var.
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change-me-in-production")

# Superset home directory for metadata DB, uploads, etc.
DATA_DIR = "/app/superset_home"

# Superset internal metadata database (SQLite stored in the named volume).
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATA_DIR}/superset.db"

# Disable the default example dashboards to keep the UI clean.
SUPERSET_LOAD_EXAMPLES = False

# Prevent connections to unsafe internal/metadata databases.
PREVENT_UNSAFE_DB_CONNECTIONS = True

# CSRF — disable for local development convenience (re-enable for production).
WTF_CSRF_ENABLED = False

# Feature flags
FEATURE_FLAGS = {
    # Disable Alerts & Reports to reduce complexity in v1.0.
    "ALERTS_ATTACH_REPORTS": False,
    # Enable native dashboard filters (required for export menu).
    "DASHBOARD_NATIVE_FILTERS": True,
    # Enable drag-and-drop chart layout in dashboard editor.
    "ENABLE_EXPLORE_DRAG_AND_DROP": True,
}

