# Phase 3: Signal Intake and Trade Decision

## Goal

Implement the core trading path from inbound scraped Telegram message to policy-gated buy execution.

This is the first phase that produces the real demo value:

- one major-asset demo case
- one regular-token demo case

## Detailed Plan

## 1. Parsing Agent

Implement the bounded parsing agent:

- message classification
- extraction into `ParsedSignal`
- confidence and reasoning summary

Keep the tool set minimal and safe.

## 2. Signal Intake Graph

Implement the LangGraph flow for:

1. ingest signal
2. parse signal
3. validate parse
4. classify asset lane
5. resolve target asset
6. enrichment agent
7. compute TA
8. decision agent
9. policy gate
10. execution
11. persistence
12. notification

The graph should follow this boundary:

- `Parsing Agent` may use skill-guided OKX reads only for parsing and token-clue resolution
- `Enrichment Agent` is the only agent in the buy path that should collect OKX-covered live context
- `Decision Agent` should not call `onchainos`; it should reason only over already-collected snapshots

## 3. OKX Adapter Implementations

Implement the production-ready OKX integration runtime for agents and deterministic nodes:

- OKX skill registry / loader
- local `onchainos` CLI runner on the server
- read-only command execution path for agent-facing tool calls
- deterministic execution path for side-effecting commands such as `swap execute`

Avoid making business-specific wrappers like `get_wallet_context` the primary model-facing integration surface.

## 4. TA Tooling

Implement application-owned TA tools:

- price deviation
- momentum
- volatility gate
- liquidity gate handoff
- composite TA score

Keep the TA system intentionally narrow for PoC.

## 5. Enrichment Agent

Implement a bounded enrichment / context collection agent:

- load OKX skills on demand
- use `run_onchainos_readonly`
- collect and normalize:
  - wallet context
  - market context
  - risk context
  - optional quote / overlay context
- output structured enrichment snapshots

This agent replaces backend-side stub collection of wallet/market/risk data.

## 6. Decision Agent

Implement the bounded decision agent:

- consume fully prepared snapshots and strategy context
- do not call `onchainos`
- do not expose OKX skill-loading tools
- no direct execution tools
- output structured `TradeDecision`

The decision agent should support both:

- major lane
- regular lane

with lane-aware prompts or middleware context.

## 7. Policy Gate

Implement the deterministic policy evaluator from:

- lane enablement
- wallet readiness
- token resolution
- risk assessment
- quote integrity
- TA thresholds
- sizing thresholds
- active position limits

This node is the final authority before execution.

## 8. Execution Path

Implement `Swap Execution Agent` flow after policy approval:

- add a shared `Swap Execution Agent`
- add restricted mutating swap tool(s) only for that agent
- call the execution agent with validated buy intent
- load `okx-dex-swap` skill
- synthesize execution request / route details from validated inputs
- invoke `swap execute` through the execution-agent tool surface
- persist execution result
- create position record
- notify Telegram

Execution planning should move out of backend-only request construction.
However:

- policy approval still remains deterministic and happens before the execution agent runs
- idempotency, persistence, and workflow control remain deterministic outside the agent

Implementation order:

1. add shared swap-execution agent and tool surface
2. refactor buy execution path to use it
3. keep persistence and position creation in deterministic nodes

## 9. Demo Support

Ensure the system can demonstrate:

- a major-asset call routed to X Layer
- a regular-token call following the full risk pipeline
- wallet readiness and balance resolution performed through `okx-agentic-wallet` skill-guided model tool calls

## Acceptance Criteria

- inbound message from webhook can trigger the full signal graph
- parsing agent outputs valid structured signal objects
- major-asset lane works end to end on X Layer when funded
- regular-token lane works end to end with:
  - token resolution
  - token scan
  - advanced-info risk enrichment
  - TA scoring
  - policy gate
- wallet, market, and risk context used for decision is obtained via the enrichment agent through model-assisted skill flow, not backend stubs
- decision agent does not call `onchainos` once enrichment snapshots are available
- execution only happens after deterministic policy approval
- buy execution uses a bounded `Swap Execution Agent` with `okx-dex-swap` skill rather than backend-only route construction
- successful execution creates:
  - trade decision record
  - trade execution record
  - position record
  - Telegram notification
- failure cases produce deterministic `skip` or `block` outcomes with reason codes
- there are integration tests for:
  - one major lane success case
  - one regular lane blocked/skipped case
  - one regular lane success case

## References

- [../prd-official.md](../prd-official.md)
- [../okx-skill-mapping.md](../okx-skill-mapping.md)
- [../architecture/core-agent-architecture.md](../architecture/core-agent-architecture.md)
- [../architecture/action-flows.md](../architecture/action-flows.md)
- [../architecture/tooling-contract.md](../architecture/tooling-contract.md)
- [../architecture/policy-spec.md](../architecture/policy-spec.md)
- [../architecture/risk-scoring-matrix.md](../architecture/risk-scoring-matrix.md)
- [../architecture/domain-schemas.md](../architecture/domain-schemas.md)
- [../architecture/config-spec.md](../architecture/config-spec.md)
