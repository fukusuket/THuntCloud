# AGENTS.md — GitHub Copilot Instructions for THuntCloud

> **THuntCloud** is a locally-executed, AI-assisted threat hunting tool for AWS CloudTrail logs.
> No SIEM required. All analysis runs locally via DuckDB.

## Project Overview

| Attribute         | Value                                                  |
| ----------------- | ------------------------------------------------------ |
| Repository        | THuntCloud                                             |
| License           | Apache License 2.0                                     |
| Primary Languages | Rust (ingester), Python (agent), Docker (orchestration) |
| Database          | DuckDB (embedded, columnar OLAP)                       |
| AI Model          | OpenAI `gpt-5.4` (configurable via `OPENAI_MODEL`)    |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐  ┌─────────────┐  │
│  │   ingester   │   │    agent     │  │  dashboard  │  │
│  │  (Rust)      │   │  (Streamlit) │  │  (Superset) │  │
│  │ READ_WRITE   │   │  READ_ONLY   │  │ READ_ONLY   │  │
│  └──────┬───────┘   └──────┬───────┘  └──────┬──────┘  │
│         └──────────────────┴──────────────────┘         │
│                            │                            │
│                    ┌───────▼──────┐                     │
│                    │   DuckDB     │                     │
│                    │  Named Vol   │                     │
│                    └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

**DuckDB Access Model:** 1 writer (`ingester`, `READ_WRITE`) / n readers (`agent`, `dashboard`, `READ_ONLY`).

## Development Methodology: TDD

This project strictly follows **Test-Driven Development**. Every feature must be developed using the Red-Green-Refactor cycle.

### Core Principles

1. **Write a test list first** — Before coding any feature, enumerate all the behaviors you want to verify as a checklist.
2. **Start from the simplest test** — Pick the easiest item from the test list and write a failing test.
3. **Red** — Run the test. It MUST fail. If it passes, the test is wrong.
4. **Green** — Write the **minimum** code to make the test pass. Ugly code is fine.
5. **Refactor** — Clean up duplication and improve design while keeping all tests green.
6. **Baby steps** — Make the smallest possible change at each step. Never skip ahead.
7. **Triangulation** — When unsure of the correct abstraction, add more specific test cases to "triangulate" toward the general solution.

### TDD Workflow for Copilot

When asked to implement a feature:

1. **Ask**: "What is the test list for this feature?"
2. **Write** a failing test (`#[test]` in Rust, `def test_*` in Python).
3. **Run** the test to confirm it fails (Red).
4. **Implement** the minimum code to pass the test (Green).
5. **Refactor** the implementation while tests remain green.
6. **Repeat** for the next item on the test list.

> **NEVER write production code without a corresponding failing test first.**

See [doc/TDD_GUIDE.md](../doc/TDD_GUIDE.md) for detailed examples.

## Key Documents

| Document | Purpose |
| -------- | ------- |
| [doc/PRD.md](../doc/PRD.md) | **Source of truth** for scope, priorities, and feature requirements |
| [doc/ARCHITECTURE.md](../doc/ARCHITECTURE.md) | System design and architectural decisions |
| [doc/TDD_GUIDE.md](../doc/TDD_GUIDE.md) | TDD methodology and worked examples |
| [doc/TESTING.md](../doc/TESTING.md) | Testing strategy per module |
| [doc/DEVELOPMENT.md](../doc/DEVELOPMENT.md) | Development setup guide |
| [ingester/AGENTS.md](../ingester/AGENTS.md) | Rust ingester module instructions |
| [agent/AGENTS.md](../agent/AGENTS.md) | Python agent module instructions |

> When in doubt about scope or priority, **always refer to the PRD first**.

## Module Reference

### ingester (Rust)

| Attribute        | Value                                            |
| ---------------- | ------------------------------------------------ |
| Path             | `ingester/`                                      |
| Language         | Rust (edition 2024)                              |
| Build            | `cargo build` / `cargo test`                     |
| Key Crates       | `serde`, `serde_json`, `flate2`, `duckdb`, `clap`, `anyhow`, `indicatif` |
| Responsibility   | Parse CloudTrail JSON/gz logs → store in DuckDB  |
| DuckDB Mode      | `READ_WRITE`                                     |

See [ingester/AGENTS.md](../ingester/AGENTS.md) for module-specific instructions.

### agent (Python / Streamlit)

| Attribute        | Value                                            |
| ---------------- | ------------------------------------------------ |
| Path             | `agent/`                                         |
| Language         | Python 3.12+                                     |
| Framework        | Streamlit                                        |
| Key Packages     | `streamlit`, `openai`, `duckdb`, `pandas`        |
| Test Framework   | `pytest`                                         |
| Responsibility   | AI-assisted threat hunting UI, SQL gen & exec    |
| DuckDB Mode      | `READ_ONLY`                                      |

See [agent/AGENTS.md](../agent/AGENTS.md) for module-specific instructions.

### dashboard (Apache Superset)

| Attribute        | Value                                            |
| ---------------- | ------------------------------------------------ |
| Path             | `dashboard/`                                     |
| Technology       | Apache Superset (Docker image)                   |
| Config           | `dashboards/` directory (YAML/ZIP exports)       |
| DuckDB Mode      | `READ_ONLY`                                      |

## Coding Conventions

### Rust (ingester)

- **Formatter**: `rustfmt` (default settings)
- **Linter**: `clippy` — all warnings must be resolved
- **Error handling**: Use `anyhow::Result` for application errors; `thiserror` for library-level custom errors
- **Tests**: Unit tests in `#[cfg(test)] mod tests` within the same file; integration tests in `ingester/tests/`
- **Naming**: snake_case for functions/variables, PascalCase for types/traits
- **Documentation**: `///` doc comments on all public items
- **Dependencies**: Prefer well-maintained crates; pin versions in `Cargo.toml`

### Python (agent)

- **Formatter**: `black` (line length 88)
- **Linter**: `ruff`
- **Type hints**: Required on all function signatures
- **Tests**: `pytest` with files under `agent/tests/`; test files named `test_*.py`
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Imports**: stdlib → third-party → local (enforce via `ruff`)
- **Docstrings**: Google style

### General

- **Commit messages**: Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`)
- **Branch naming**: `feature/<module>-<short-desc>`, `fix/<module>-<short-desc>`
- **PR scope**: One logical change per PR; include test changes alongside production code

## DuckDB Access Patterns

### Connection Strings

```python
# Agent / Dashboard (READ_ONLY)
conn = duckdb.connect("/data/db/threat_hunting.db", read_only=True)
```

```rust
// Ingester (READ_WRITE)
let db = Connection::open("/data/db/threat_hunting.db")?;
```

### Important Rules

1. **Never open READ_WRITE from agent or dashboard** — this will conflict with the ingester lock.
2. **Ingester must be run first**, then agent/dashboard query the data.
3. **Tests must use temporary databases** — use `tempfile` (Rust) or `tmp_path` (pytest) to create isolated DuckDB files.
4. **SSD storage is strongly recommended** for the DuckDB volume.

## CloudTrail Table Schema (Reference)

The ingester creates a `cloudtrail_events` table:

```sql
CREATE TABLE IF NOT EXISTS cloudtrail_events (
    event_time           TIMESTAMP,
    event_name           VARCHAR,
    event_source         VARCHAR,
    aws_region           VARCHAR,
    source_ip_address    VARCHAR,
    user_agent           VARCHAR,
    user_identity_type   VARCHAR,
    user_identity_arn    VARCHAR,
    user_identity_account_id VARCHAR,
    request_parameters   JSON,
    response_elements    JSON,
    error_code           VARCHAR,
    error_message        VARCHAR,
    read_only            BOOLEAN,
    event_type           VARCHAR,
    recipient_account_id VARCHAR,
    raw_event            JSON
);
```

## Security Rules

1. **API keys**: Never hardcode OpenAI API keys. Always read from environment variables or `.env` file.
2. **SQL injection prevention**: Agent module opens DuckDB in `READ_ONLY` mode. Run `EXPLAIN` before executing AI-generated SQL to validate it.
3. **No cloud upload**: v1.0 has no functionality to send data externally (except OpenAI API calls for SQL generation).
4. **Network**: All services are local-only; no ports exposed to the public internet.

## File Structure

```
THuntCloud/
├── .github/
│   └── AGENTS.md              ← You are here
├── ingester/                  # Rust log ingestion engine
│   ├── AGENTS.md              # Module-specific Copilot instructions
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs
│   │   ├── parser.rs          # CloudTrail JSON parsing
│   │   ├── decompressor.rs    # gz decompression
│   │   ├── db.rs              # DuckDB operations
│   │   └── ingest.rs          # Orchestration logic
│   └── tests/
│       ├── integration_test.rs
│       └── testdata/          # Sample CloudTrail JSON/gz files
├── agent/                     # Streamlit AI-Agent UI
│   ├── AGENTS.md              # Module-specific Copilot instructions
│   ├── app.py                 # Streamlit entry point
│   ├── llm.py                 # OpenAI API integration
│   ├── query.py               # DuckDB query execution
│   ├── report.py              # Report generation
│   ├── prompts/               # Built-in prompt templates
│   ├── requirements.txt
│   └── tests/
│       ├── conftest.py
│       ├── test_llm.py
│       ├── test_query.py
│       └── test_report.py
├── dashboard/                 # Superset config
├── dashboards/                # Pre-built dashboards (YAML/ZIP)
├── data/                      # Log data (git-ignored)
├── docker/
│   └── docker-compose.yml
├── doc/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── TDD_GUIDE.md
│   └── TESTING.md
└── .env.example
```

## Quick Reference Commands

```bash
# Run ingester tests
cd ingester && cargo test

# Run agent tests
cd agent && pytest

# Build and start all services
cd docker && docker compose up -d

# Run ingester to load logs
cd docker && docker compose --profile ingest run --rm ingester ingest --path /data/logs

# Lint (Rust)
cd ingester && cargo clippy -- -D warnings

# Lint (Python)
cd agent && ruff check .

# Format (Rust)
cd ingester && cargo fmt --check

# Format (Python)
cd agent && black --check .
```

