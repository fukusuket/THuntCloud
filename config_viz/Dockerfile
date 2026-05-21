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
# node:22-slim (Active LTS) — pinned by digest for supply chain integrity.
# To update: docker pull node:22-slim && docker inspect node:22-slim --format '{{index .RepoDigests 0}}'
# See doc/SUPPLY_CHAIN_HARDENING.md Phase 3.
FROM node:22-slim@sha256:7af03b14a13c8cdd38e45058fd957bf00a72bbe17feac43b1c15a689c029c732 AS frontend-builder

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
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app/frontend

# Install dependencies first for layer caching
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci

# Generate CycloneDX SBOM for supply chain provenance (Phase 5).
# Placed after npm ci so it captures the exact installed graph.
RUN npx --yes @cyclonedx/cyclonedx-npm \
      --output-format JSON \
      --output-file /tmp/sbom-frontend.json \
      --mc-type application 2>/dev/null \
    && echo "SBOM generated: $(wc -c < /tmp/sbom-frontend.json) bytes"

# Copy source and build
# vite.config.ts: outDir = path.resolve(__dirname, "../static")
# → output goes to /app/static/
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

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

# Copy SBOM for provenance / compliance audits
COPY --from=frontend-builder /tmp/sbom-frontend.json ./sbom-frontend.json

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

