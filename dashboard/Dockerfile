# Custom Apache Superset image with DuckDB support.
# Installs duckdb-engine (SQLAlchemy dialect) and the duckdb Python package
# so that DuckDB appears as a connectable database inside Superset.
FROM apache/superset:4.1.4

USER root

# ── (Proxy) Custom CA certificate ─────────────────────────────────────────────
# If you are behind a corporate proxy that performs TLS inspection,
# uncomment the following lines and place your CA certificate file
# (e.g. custom-ca.crt) in the same directory as this Dockerfile.
#
# COPY custom-ca.crt /usr/local/share/ca-certificates/custom-ca.crt
# RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
#     && update-ca-certificates \
#     && rm -rf /var/lib/apt/lists/*
# ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
# ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
# ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
# ──────────────────────────────────────────────────────────────────────────────

RUN pip install --no-cache-dir \
    "duckdb>=1.2.0" \
    "duckdb-engine>=0.13.0"

USER superset

