# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM rust:1.85-slim AS builder

# Install build dependencies required by duckdb (bundled feature compiles C++)
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    cmake \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache dependencies by copying manifests first
COPY Cargo.toml Cargo.lock ./

# Create a dummy main.rs so cargo can fetch and compile dependencies
RUN mkdir src && echo 'fn main() {}' > src/main.rs
RUN cargo build --release --locked 2>/dev/null || true

# Now copy the real source and build
COPY src ./src
RUN touch src/main.rs && cargo build --release --locked

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/target/release/ingester /usr/local/bin/ingester

ENTRYPOINT ["ingester"]
CMD ["--help"]

