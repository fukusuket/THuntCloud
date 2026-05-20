FROM python:3.14-slim

WORKDIR /app

# ── (Proxy) Custom CA certificate ─────────────────────────────────────────────
# No edits needed here. To enable proxy support for all containers at once:
#   1. Base64-encode your CA cert:
#        macOS : CUSTOM_CA_CERT_BASE64=$(base64 -i /path/to/custom-ca.crt)
#        Linux : CUSTOM_CA_CERT_BASE64=$(base64 -w0 /path/to/custom-ca.crt)
#   2. Add the result to docker/.env:
#        CUSTOM_CA_CERT_BASE64=<value>
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

# Install curl for HEALTHCHECK and other runtime tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install runtime dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

