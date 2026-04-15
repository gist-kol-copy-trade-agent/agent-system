# System

Runtime for the implementation described across `../architecture/` and `../implementation-plan/`.

This directory contains:

- Python application package in `app/`
- migration skeleton in `migrations/`
- test suite in `tests/`

The code here is runnable for supervised operation and integration verification, but it still has explicit boundaries:

- LangGraph orchestration is implemented for signal intake, exit evaluation, and command flows.
- execution and policy gates are deterministic after the agent decision boundary.
- default checkpoint durability uses the Postgres LangGraph checkpointer when installed with runtime dependencies.
- the container image installs the `onchainos` CLI at build time via the official OKX installer script, so runtime tool calls do not depend on a host-level binary.

Current runtime shape:

- HTTP app only for scraper webhook + health/readiness
- Telegram bot runtime as a separate polling process
- core trading and exit workflows run through LangGraph-backed services in `app/services/`
- `/readiness` exposes both component checks and `trading_runtime_ready` for execution-critical preflight status
- `python -m app.workers.preflight` provides an operator/CI-friendly preflight that exits non-zero when trading readiness is not met

Persistence:

- default runtime database is PostgreSQL via `OKX_AGENT_PERSISTENCE__DATABASE_URL`
- tests override this to SQLite in-memory through `tests/conftest.py`

Default local DSN:

```bash
export OKX_AGENT_PERSISTENCE__DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/okx_agent
```

Quick start with local Postgres:

```bash
docker compose -f docker-compose.standalone.yml up -d postgres
```

Operational docs:

- Env template: `.env.standalone.example`
- Container build: `Dockerfile`
- Standalone runtime stack: `docker-compose.standalone.yml`
- Reproducible local dev/test flow: use the root `Makefile` with a dedicated `system` virtualenv

Container note:

- `Dockerfile` installs the latest stable `onchainos` CLI using the official installer script from `okx/onchainos-skills`
- this keeps the container self-contained for runtime execution
- if stricter build reproducibility is needed later, pinning a specific CLI release would be the next step
