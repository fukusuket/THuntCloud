# ── config_viz — Multi-stage Dockerfile ──────────────────────────────────────
#
# Stage 1: frontend-builder  — builds the React/Vite SPA → /app/static/
# Stage 2: runtime           — Python 3.12 + FastAPI + built static files
#
# The /icons/ endpoint is populated at build time by extract_icons.py.
# If the download fails (no network, TLS proxy, etc.) the build still succeeds
# and the frontend falls back to /icons/default.png for all resource types.
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Install dependencies first for layer caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy source and build
# vite.config.ts: outDir = path.resolve(__dirname, "../static")
# → output goes to /app/static/
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

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
# ──────────────────────────────────────────────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python runtime dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source (includes scripts/extract_icons.py)
COPY backend/ ./backend/

# Copy Vite build artefacts from Stage 1
COPY --from=frontend-builder /app/static ./static

# Fetch AWS service icons at build time.
# Failure (e.g. no internet access) is acceptable — extract_icons.py always
# creates default.png and exits 0; the frontend falls back to that file.
RUN python backend/scripts/extract_icons.py /app/static/icons || true

EXPOSE 8502

# Default DB path — override with DUCKDB_PATH env var or a docker-compose binding
ENV DUCKDB_PATH=/data/db/threat_hunting.db

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8502/api/snapshots || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8502"]

