# Custom Apache Superset image with DuckDB support.
# Installs duckdb-engine (SQLAlchemy dialect) so that DuckDB appears as a
# connectable database inside Superset.
#
# DU-01: Base image upgraded to Superset 6.1.0 (SQLAlchemy 2.x).
# DU-02: duckdb-engine>=0.14.0 required for SQLAlchemy 2.x compatibility.
# DU-16: --break-system-packages handles PEP 668 externally-managed-environment
#        restriction in Python 3.11+. Explicit duckdb pin removed to avoid
#        version conflicts with packages pre-installed in Superset 6.x.
# DU-17: Build-time import check catches missing-module errors early.
FROM apache/superset:6.1.0

USER root

# ── (Proxy) Custom CA certificate ─────────────────────────────────────────────
# No edits needed here. Set CUSTOM_CA_CERT_BASE64 in docker/.env to enable.
# See docker/.env.example for instructions.
# ──────────────────────────────────────────────────────────────────────────────
ARG CUSTOM_CA_CERT_BASE64=""
RUN if [ -n "$CUSTOM_CA_CERT_BASE64" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends ca-certificates \
        && printf '%s' "$CUSTOM_CA_CERT_BASE64" | base64 -d \
             > /usr/local/share/ca-certificates/custom-ca.crt \
        && update-ca-certificates \
        && rm -rf /var/lib/apt/lists/*; \
    fi
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# DU-02/DU-16: Install duckdb-engine into the uv-managed venv at /app/.venv.
# Superset 6.x uses uv (not pip) to manage the virtual environment.
# The venv intentionally has no pip module (uv-managed venvs omit it by default),
# so both `pip install` and `python3 -m pip install` fail at build time.
# uv is present in the final image (inherited via the lean build stage) and is
# the correct tool to target /app/.venv directly.
# No --break-system-packages flag: uv installs into the isolated venv, not the
# system Python, so PEP 668 (externally-managed-environment) does not apply.
RUN uv pip install --python /app/.venv --no-cache-dir \
    "duckdb-engine>=0.14.0"

# DU-17: Verify the dialect is importable at build time.
RUN python3 -c 'import duckdb_engine'

USER superset

