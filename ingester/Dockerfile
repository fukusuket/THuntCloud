# ── Stage 1: Builder ──────────────────────────────────────────────────────────
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

# Install build dependencies (cmake/g++ no longer needed — prebuilt libduckdb is downloaded)
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Download prebuilt libduckdb instead of compiling C++ from source.
# This drastically reduces build time and memory usage (safe for WSL2 / low-RAM envs).
ENV DUCKDB_DOWNLOAD_LIB=1

WORKDIR /app

# Cache dependencies by copying manifests first
COPY Cargo.toml Cargo.lock ./

# Create a dummy main.rs so cargo can fetch and compile dependencies.
RUN mkdir src && echo 'fn main() {}' > src/main.rs
RUN cargo build --release --locked || true

# Now copy the real source and build
COPY src ./src
RUN touch src/main.rs && cargo build --release --locked

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/target/release/ingester /usr/local/bin/ingester
# Copy the prebuilt libduckdb shared library required at runtime.
# DUCKDB_DOWNLOAD_LIB=1 places the .so in target/release/deps/ via copy_libduckdb().
COPY --from=builder /app/target/release/deps/libduckdb.so /usr/local/lib/libduckdb.so
RUN ldconfig

ENTRYPOINT ["ingester"]
CMD ["--help"]

