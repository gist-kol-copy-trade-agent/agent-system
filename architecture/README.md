# Architecture Docs

## Scope

This folder defines the internal agent architecture for the PoC/V1 product:

- built on LangChain agents,
- running on LangGraph runtime,
- using OKX OnchainOS skills through application-owned tool wrappers,
- optimized for `authorized-auto` execution only.

## Documents

- [design-principles.md](design-principles.md): the architecture north star for dividing responsibilities between LangChain and LangGraph.
- [core-agent-architecture.md](core-agent-architecture.md): overall agent topology, LangChain/LangGraph design, node boundaries, and tool exposure rules.
- [action-flows.md](action-flows.md): per-action interaction flow showing when the model is called, which tools are exposed, and which steps stay deterministic.
- [domain-schemas.md](domain-schemas.md): normalized internal domain objects for parsed signals, resolutions, enrichment, decisions, execution, and graph state.
- [policy-spec.md](policy-spec.md): deterministic skip/block/execute rules, lane behavior, sizing logic, and fallback exit policy.
- [risk-scoring-matrix.md](risk-scoring-matrix.md): default interpretation matrix for regular-token risk using `okx-security` and `okx-dex-token advanced-info`.
- [config-spec.md](config-spec.md): runtime configuration surface for thresholds, presets, integration settings, execution defaults, and policy knobs.
- [persistence-schema.md](persistence-schema.md): PostgreSQL table contract, indexes, idempotency keys, and query-oriented storage design.
- [telegram-command-contract.md](telegram-command-contract.md): supported Telegram commands, accepted input shapes, outputs, state mutations, and model usage policy.
- [scraper-integration-contract.md](scraper-integration-contract.md): webhook and register/unregister API contract between the bot and the Telegram scraper service.
- [state-and-persistence.md](state-and-persistence.md): what belongs in short-term state, long-term store, and the application persistence layer.
- [tooling-contract.md](tooling-contract.md): tool taxonomy and the tool interfaces the LangChain agent should call.
- [user-strategy-profile-schema.md](user-strategy-profile-schema.md): normalized schema for user trading style and resolved global strategy parameters.

## LangChain Basis

This design is intentionally aligned with current LangChain / LangGraph guidance from the `langchain-docs` MCP, especially:

- `oss/python/langchain/agents`
- `oss/python/langchain/context-engineering`
- `oss/python/langchain/runtime`
- `oss/python/concepts/memory`
- `oss/python/langgraph/overview`
- `oss/python/langgraph/persistence`

## Main Design Choice

The system should not be a single free-form general-purpose agent with unrestricted trading tools.

Instead:

- use LangChain `create_agent` for bounded reasoning loops,
- use LangGraph runtime and checkpoints for durable orchestration,
- keep critical trading steps behind deterministic graph nodes and policy gates,
- expose only the minimum safe tool subset to the model at each stage.
