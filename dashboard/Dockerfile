# Custom Apache Superset image with DuckDB support.
# Installs duckdb-engine (SQLAlchemy dialect) and the duckdb Python package
# so that DuckDB appears as a connectable database inside Superset.
FROM apache/superset:4.1.2

USER root

RUN pip install --no-cache-dir \
    "duckdb>=1.2.0" \
    "duckdb-engine>=0.13.0"

USER superset

