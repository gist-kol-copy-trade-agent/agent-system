# Phase 1: Foundation and Contracts

## Goal

Create the implementation foundation so later phases can build features without redefining core contracts.

This phase should produce:

- project skeleton,
- executable schema layer,
- config loading,
- persistence models and migrations,
- LangGraph/LangChain runtime skeleton,
- adapter and tool boundaries.

## Detailed Plan

## 1. Project Skeleton

Create the base package layout.

Recommended structure:

```text
app/
  agents/
  graphs/
  tools/
  adapters/
    okx/
    scraper/
    telegram/
  policies/
  schemas/
  persistence/
  services/
  config/
  workers/
  observability/
tests/
migrations/
```

## 2. Schema Layer

Implement code schemas from the architecture docs:

- graph state
- parsed signal
- resolved asset
- wallet snapshot
- market snapshot
- risk snapshot
- TA snapshot
- trade decision
- policy gate result
- execution request/result
- strategy profile
- scraper webhook payload

Use one schema style consistently:

- `TypedDict` for graph state and agent-facing light contracts
- Pydantic models for external payload validation and persistence DTOs

## 3. Config Layer

Implement config loading based on:

- environment config
- execution defaults
- policy thresholds
- risk matrix thresholds
- strategy presets

Config should support:

- local development
- staging
- production-like settings later

## 4. Persistence Foundation

Implement the initial database and migration layer:

- SQLAlchemy models or equivalent
- migrations for core tables
- repository interfaces for key aggregates

Priority tables:

- `users`
- `wallet_sessions`
- `user_strategy_profiles`
- `followed_sources`
- `source_messages`
- `parsed_signal_candidates`
- `asset_resolutions`
- `enrichment_snapshots`
- `trade_decisions`
- `trade_executions`
- `positions`
- `position_events`
- `workflow_runs`
- `audit_events`

## 5. LangGraph Runtime Skeleton

Implement:

- checkpointer setup
- graph thread id conventions
- base runtime context object
- empty graph skeletons for:
  - command flows
  - signal intake flow
  - position monitoring flow

## 6. Tool and Skill Boundaries

Implement empty or stubbed interfaces for:

- OKX skill registry / loader
- generic read-only `onchainos` command boundary
- scraper client
- Telegram notifier
- model-facing tools
- policy evaluators

The goal is not to finish business logic here, but to lock interfaces.

## 7. Observability Skeleton

Implement:

- structured logging
- LangSmith tracing hooks
- workflow run logging
- audit event writing helper

## Acceptance Criteria

- repository has a stable app structure with clear module ownership
- all critical domain contracts from architecture exist as code schemas
- config can be loaded from one central place
- DB migrations can create the core schema on a clean database
- LangGraph runtime can initialize with checkpointer and thread id conventions
- adapter/tool/policy interfaces exist and compile even if some methods are stubbed
- there is at least one smoke test proving app startup and migration success

## References

- [../architecture/domain-schemas.md](../architecture/domain-schemas.md)
- [../architecture/persistence-schema.md](../architecture/persistence-schema.md)
- [../architecture/config-spec.md](../architecture/config-spec.md)
- [../architecture/core-agent-architecture.md](../architecture/core-agent-architecture.md)
- [../architecture/state-and-persistence.md](../architecture/state-and-persistence.md)
- [../architecture/tooling-contract.md](../architecture/tooling-contract.md)
- [../architecture/design-principles.md](../architecture/design-principles.md)
