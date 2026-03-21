# ── Build arg: set to a release tag (e.g. v0.1.3) to download a prebuilt
# binary from GitHub Releases and skip Rust compilation entirely.
# Used by the `prebuilt-runtime` target below.
# Leave empty (default) to compile from source with the `runtime` target.
ARG INGESTER_VERSION="v0.1.3"

# ── Stage 1: Builder (compile from source) ────────────────────────────────────
FROM rust:1.94-slim AS builder

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
# ENV CARGO_HTTP_CAINFO=/etc/ssl/certs/ca-certificates.crt
# ──────────────────────────────────────────────────────────────────────────────

# Install build dependencies required by duckdb (bundled feature compiles C++)
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    cmake \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Limit parallel C++ compilation jobs to prevent OOM on memory-constrained
# environments (e.g. WSL2 defaults to 2 GB RAM).
# Increase or remove this if you have ≥16 GB RAM available.
ENV CARGO_BUILD_JOBS=2

WORKDIR /app

# Cache dependencies by copying manifests first
COPY Cargo.toml Cargo.lock ./

# Create a dummy main.rs so cargo can fetch and compile dependencies.
RUN mkdir src && echo 'fn main() {}' > src/main.rs
RUN cargo build --release --locked || true

# Now copy the real source and build
COPY src ./src
RUN touch src/main.rs && cargo build --release --locked

# ── Stage 2: Runtime (source build) ──────────────────────────────────────────
FROM debian:trixie-slim AS runtime

# ── (Proxy) Custom CA certificate ─────────────────────────────────────────────
# If you are behind a corporate proxy, uncomment the following lines.
#
# COPY custom-ca.crt /usr/local/share/ca-certificates/custom-ca.crt
# RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
#     && update-ca-certificates \
#     && rm -rf /var/lib/apt/lists/*
# ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
# ──────────────────────────────────────────────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libstdc++6 \
    libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/target/release/ingester /usr/local/bin/ingester

ENTRYPOINT ["ingester"]
CMD ["--help"]

# ── Stage 3: Prebuilt binary downloader ───────────────────────────────────────
# Downloads the ingester binary from a tagged GitHub Release.
# Only used when the `prebuilt-runtime` build target is selected.
# TARGETARCH is set automatically by Docker BuildKit (amd64 / arm64).
FROM debian:trixie-slim AS downloader
ARG INGESTER_VERSION
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN test -n "$INGESTER_VERSION" || { echo "Error: INGESTER_VERSION build arg must be set"; exit 1; } \
    && case "$TARGETARCH" in \
        amd64) BINARY="ingester-x86_64-linux"  ;; \
        arm64) BINARY="ingester-aarch64-linux" ;; \
        *)     echo "Error: unsupported architecture: $TARGETARCH"; exit 1 ;; \
    esac \
    && BASE_URL="https://github.com/fukusuket/THuntCloud/releases/download/${INGESTER_VERSION}" \
    && curl -fsSL -o /tmp/${BINARY}          "${BASE_URL}/${BINARY}" \
    && curl -fsSL -o /tmp/${BINARY}.sha256   "${BASE_URL}/${BINARY}.sha256" \
    && (cd /tmp && sha256sum -c ${BINARY}.sha256) \
    && install -m 755 /tmp/${BINARY} /usr/local/bin/ingester \
    && rm /tmp/${BINARY} /tmp/${BINARY}.sha256

# ── Stage 4: Prebuilt runtime ─────────────────────────────────────────────────
# Uses the binary downloaded by Stage 3 — the Rust builder stage is NOT
# executed when Docker BuildKit resolves this target.
#
# Usage (from docker/ directory):
#   INGESTER_BUILD_TARGET=prebuilt-runtime INGESTER_VERSION=v0.1.3 \
#     docker compose build ingester
FROM debian:trixie-slim AS prebuilt-runtime

# ── (Proxy) Custom CA certificate ─────────────────────────────────────────────
# If you are behind a corporate proxy, uncomment the following lines.
#
# COPY custom-ca.crt /usr/local/share/ca-certificates/custom-ca.crt
# RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
#     && update-ca-certificates \
#     && rm -rf /var/lib/apt/lists/*
# ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
# ──────────────────────────────────────────────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libstdc++6 \
    libgcc-s1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=downloader /usr/local/bin/ingester /usr/local/bin/ingester

ENTRYPOINT ["ingester"]
CMD ["--help"]
