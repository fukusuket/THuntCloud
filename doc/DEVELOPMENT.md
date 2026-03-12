# Development Guide

## Language Policy

All contributions to this project MUST use English for:

- Source code comments (`//`, `///`, `//!` in Rust; `#` and docstrings in Python)
- Documentation files (`.md`, `.txt`, `.rst`)
- Commit messages and PR descriptions

Non-English text anywhere in the codebase or version history is not permitted.

## Prerequisites

| Tool              | Version      | Purpose                              |
| ----------------- | ------------ | ------------------------------------ |
| Rust              | 1.85+        | ingester development                 |
| Python            | 3.12+        | agent development                    |
| Docker Desktop    | Latest       | Container orchestration              |
| Docker Compose    | v2           | Multi-service management             |
| DuckDB CLI        | 1.2+         | (Optional) Ad-hoc database inspection|
| Git               | 2.40+        | Version control                      |

## Initial Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/THuntCloud.git
cd THuntCloud
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and set:
#   OPENAI_API_KEY=sk-...
#   OPENAI_MODEL=gpt-5.4         (optional, default)
#   SUPERSET_SECRET_KEY=...       (optional for dev)
```

### 3. ingester (Rust) Setup

```bash
cd ingester

# Install Rust toolchain (if not installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Verify
rustc --version    # 1.85+
cargo --version

# Build
cargo build

# Run tests
cargo test

# Lint
cargo clippy -- -D warnings

# Format check
cargo fmt --check
```

### 4. agent (Python) Setup

```bash
cd agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest

# Lint
ruff check .

# Format check
black --check .
```

### 5. Docker Compose (Full Stack)

```bash
cd docker

# Build all services
docker compose build

# Start agent + dashboard
docker compose up -d

# Run ingester to load logs
docker compose --profile ingest run --rm ingester ingest --path /data/logs

# View logs
docker compose logs -f agent
docker compose logs -f superset

# Stop
docker compose down
```

## Development Workflow

### TDD Cycle (Every Feature)

This project follows **TDD**. Every code change must follow the Red-Green-Refactor cycle.

```
1. Write test list        → Enumerate expected behaviors
2. Pick simplest test     → Write a failing test
3. Red                    → Run test, confirm FAIL
4. Green                  → Write minimum code to pass
5. Refactor               → Clean up, keep tests green
6. Repeat                 → Next test from the list
```

See [TDD_GUIDE.md](TDD_GUIDE.md) for detailed methodology and examples.

### Module-Specific Development

#### ingester (Rust)

```bash
cd ingester

# TDD loop
cargo test                        # Run all tests
cargo test test_name              # Run a specific test
cargo test -- --nocapture         # See println! output
cargo test -- --test-threads=1    # Run tests sequentially

# Watch mode (requires cargo-watch)
cargo install cargo-watch
cargo watch -x test               # Auto-run tests on file change
```

#### agent (Python)

```bash
cd agent
source .venv/bin/activate

# TDD loop
pytest                            # Run all tests
pytest tests/test_query.py        # Run a specific test file
pytest -k "test_connect"          # Run tests matching a pattern
pytest -v                         # Verbose output
pytest --tb=short                 # Short traceback

# Watch mode (requires pytest-watch)
pip install pytest-watch
ptw                               # Auto-run tests on file change
```

## Directory Convention

```
THuntCloud/
├── .github/
│   └── AGENTS.md              # Copilot Agents root instructions
├── ingester/
│   ├── AGENTS.md              # Module-specific Copilot instructions
│   ├── Cargo.toml             # Rust dependencies
│   ├── src/                   # Source code
│   │   ├── main.rs            # CLI entry point
│   │   ├── lib.rs             # Library root
│   │   ├── parser.rs          # CloudTrail JSON parsing
│   │   ├── decompressor.rs    # gz decompression
│   │   ├── db.rs              # DuckDB operations
│   │   ├── ingest.rs          # Orchestration
│   │   └── progress.rs        # Progress display
│   └── tests/
│       ├── integration_test.rs
│       └── testdata/          # Sample CloudTrail files
├── agent/
│   ├── AGENTS.md              # Module-specific Copilot instructions
│   ├── app.py                 # Streamlit entry point
│   ├── llm.py                 # OpenAI integration
│   ├── query.py               # DuckDB query execution
│   ├── report.py              # Report generation
│   ├── requirements.txt       # Python dependencies
│   ├── requirements-dev.txt   # Dev dependencies
│   └── tests/                 # pytest tests
├── dashboard/                 # Superset config + pre-built dashboard assets
│   ├── assets/                # Dashboard definitions and ZIP exports
├── data/                      # Log data (git-ignored)
├── docker/
│   └── docker-compose.yml     # Orchestration
└── doc/                       # Documentation
```

## CI Pipeline (Expected)

The CI pipeline should enforce the following stages:

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│  Lint    │───▶│  Test    │───▶│  Build   │
│          │    │          │    │          │
│ clippy   │    │ cargo    │    │ docker   │
│ rustfmt  │    │   test   │    │ compose  │
│ ruff     │    │ pytest   │    │   build  │
│ black    │    │          │    │          │
└──────────┘    └──────────┘    └──────────┘
```

### Stage Details

| Stage  | ingester (Rust)                   | agent (Python)              |
| ------ | --------------------------------- | --------------------------- |
| Lint   | `cargo clippy -- -D warnings`     | `ruff check .`              |
| Format | `cargo fmt --check`               | `black --check .`           |
| Test   | `cargo test`                      | `pytest`                    |
| Build  | `cargo build --release`           | N/A (interpreted)           |
| Docker | `docker build -t ingester .`      | `docker build -t agent .`   |

## Useful Commands

```bash
# Inspect DuckDB directly (requires DuckDB CLI)
duckdb data/db/threat_hunting.db "SELECT COUNT(*) FROM cloudtrail_events"

# View table schema
duckdb data/db/threat_hunting.db ".schema cloudtrail_events"

# Quick data check
duckdb data/db/threat_hunting.db "SELECT * FROM cloudtrail_events LIMIT 5"

# Docker volume inspection
docker volume inspect threat-hunting-duckdb
```

## Environment Variables Reference

| Variable              | Module    | Default          | Description                            |
| --------------------- | --------- | ---------------- | -------------------------------------- |
| `DUCKDB_PATH`         | all       | (required)       | Path to DuckDB file                    |
| `DUCKDB_READONLY`     | agent     | `true`           | Force read-only mode                   |
| `OPENAI_API_KEY`      | agent     | (required)       | OpenAI API key                         |
| `OPENAI_MODEL`        | agent     | `gpt-5.4`       | Primary AI model                       |
| `OPENAI_MODEL_LITE`   | agent     | `gpt-5.4-mini`  | Lightweight model                      |
| `RUST_LOG`            | ingester  | `info`           | Rust log level                         |
| `SUPERSET_SECRET_KEY` | dashboard | `change-me-...`  | Superset secret                        |

