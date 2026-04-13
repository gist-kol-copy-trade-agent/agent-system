# System

Phase 1 scaffold for the implementation described in `../implementation-plan/phase-1-foundation-and-contracts.md`.

This directory contains:

- Python application package in `app/`
- migration skeleton in `migrations/`
- smoke tests in `tests/`

The code here is intentionally skeletal. It locks interfaces and contracts before feature work in later phases.

Current runtime shape:

- HTTP app only for scraper webhook + health/readiness
- Telegram bot runtime as a separate polling process
- core trading and exit workflows run through LangGraph-backed services in `app/services/`

Persistence:

- default runtime database is PostgreSQL via `OKX_AGENT_PERSISTENCE__DATABASE_URL`
- tests override this to SQLite in-memory through `tests/conftest.py`

Default local DSN:

```bash
export OKX_AGENT_PERSISTENCE__DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/okx_agent
```

Quick start with local Postgres:

```bash
docker compose up -d postgres
```
