"""Tests for Dockerfile — verify Superset 6.1 base image and dependency pins.

DU-01: Base image tag must be apache/superset:6.1.x
DU-02: duckdb-engine version constraint must be >=0.14.0
DU-16: pip install must use --break-system-packages to handle PEP 668 (externally-managed
       environment restriction in Python 3.11+) and must NOT pin an explicit duckdb
       version (to avoid conflicts with packages already installed in Superset 6.x).
DU-17: Dockerfile must verify 'import duckdb_engine' at Docker build time.
"""

import os
import re

DOCKERFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")


def _read_dockerfile() -> str:
    with open(DOCKERFILE_PATH, encoding="utf-8") as fh:
        return fh.read()


def test_dockerfile_base_image_is_61() -> None:
    """DU-01: FROM line must reference apache/superset 6.1.x."""
    content = _read_dockerfile()
    assert re.search(r"FROM apache/superset:6\.1\.", content), (
        "Dockerfile base image must be apache/superset:6.1.x — "
        f"update FROM line.  Current content:\n{content[:300]}"
    )


def test_duckdb_engine_version_constraint() -> None:
    """DU-02: duckdb-engine must be pinned to >=0.14.0 for SQLAlchemy 2.x support."""
    content = _read_dockerfile()
    assert re.search(r"duckdb-engine[><=!]+0\.1[4-9]", content), (
        "duckdb-engine must be >=0.14.0 for SQLAlchemy 2.x (Superset 6.x) support. "
        f"Current Dockerfile RUN block does not match.  Content:\n{content}"
    )


def test_pip_uses_break_system_packages() -> None:
    """DU-16: pip install must include --break-system-packages.

    Two failure modes require this flag:

    1. PEP 668 (externally-managed-environment):
       Some Superset 6.x images are based on Debian bookworm with Python marked as
       externally managed.  pip install fails with exit code 1 and:
           error: externally-managed-environment
       Fix: add --break-system-packages.

    2. duckdb version conflict:
       Superset 6.x may already have duckdb installed at a specific version.
       Pinning duckdb>=1.2.0 can cause pip's dependency resolver to fail.
       Fix: remove the explicit duckdb pin — let duckdb-engine pull in a
       compatible version as its own dependency.
    """
    content = _read_dockerfile()
    assert "--break-system-packages" in content, (
        "Dockerfile pip install must include --break-system-packages to handle:\n"
        "  1. PEP 668 externally-managed-environment restriction\n"
        "  2. duckdb version conflict with Superset 6.x pre-installed packages\n"
        "Add: pip install --break-system-packages --no-cache-dir ..."
    )


def test_no_explicit_duckdb_pin() -> None:
    """DU-16b: Dockerfile must NOT pin an explicit duckdb (non-engine) version.

    Pinning 'duckdb>=1.2.0' on top of duckdb-engine causes pip dependency resolver
    conflicts in Superset 6.x where duckdb is already an indirect dependency.
    duckdb-engine>=0.14.0 pulls in a compatible duckdb version automatically.
    """
    content = _read_dockerfile()
    # Match a bare duckdb install line (not duckdb-engine)
    # Allow "duckdb" only as part of "duckdb-engine" or in comments/import checks
    install_lines = [
        line
        for line in content.splitlines()
        if not line.strip().startswith("#")
        and re.search(r'"duckdb[>=<!]', line)
        and "duckdb-engine" not in line
        and "import duckdb" not in line
    ]
    assert not install_lines, (
        f"Dockerfile must not pin a standalone duckdb version — it conflicts with "
        f"packages already present in Superset 6.x.  Offending lines: {install_lines}\n"
        "Remove 'duckdb>=X.Y.Z' and let duckdb-engine manage the duckdb dependency."
    )


def test_dockerfile_verifies_import_at_build_time() -> None:
    """DU-17: Dockerfile must verify 'import duckdb_engine' succeeds during docker build.

    A build-time import check catches the 'No module named duckdb_engine' error before
    the container starts, giving a clear error in docker build output rather than a
    cryptic Superset runtime error.
    """
    content = _read_dockerfile()
    assert "import duckdb_engine" in content, (
        "Dockerfile must include a build-time verification step:\n"
        "  python3 -c 'import duckdb_engine'\n"
        "This ensures missing-module errors are detected during docker build."
    )
