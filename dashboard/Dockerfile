# Custom Apache Superset image with DuckDB support.
# Installs duckdb-engine (SQLAlchemy dialect) and the duckdb Python package
# so that DuckDB appears as a connectable database inside Superset.
FROM apache/superset:4.1.4

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

RUN pip install --no-cache-dir \
    "duckdb>=1.2.0" \
    "duckdb-engine>=0.13.0"

USER superset

