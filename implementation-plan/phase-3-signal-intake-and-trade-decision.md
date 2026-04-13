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
6. load wallet context
7. fetch market context
8. compute TA
9. fetch optional signal overlay
10. run conditional risk checks
11. decision agent
12. policy gate
13. execution
14. persistence
15. notification

## 3. OKX Adapter Implementations

Implement production-ready wrappers for:

- wallet context fetch
- token search and price info
- token advanced info
- security token scan
- market price and kline
- signal list
- swap quote
- swap execute

Normalize outputs into internal schema objects.

## 4. TA Tooling

Implement application-owned TA tools:

- price deviation
- momentum
- volatility gate
- liquidity gate handoff
- composite TA score

Keep the TA system intentionally narrow for PoC.

## 5. Decision Agent

Implement the bounded decision agent:

- consume structured context only
- no direct execution tools
- output structured `TradeDecision`

The decision agent should support both:

- major lane
- regular lane

with lane-aware prompts or middleware context.

## 6. Policy Gate

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

## 7. Execution Path

Implement deterministic execution nodes:

- build execution request
- submit buy via `swap execute`
- persist execution result
- create position record
- notify Telegram

## 8. Demo Support

Ensure the system can demonstrate:

- a major-asset call routed to X Layer
- a regular-token call following the full risk pipeline

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
- execution only happens after deterministic policy approval
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
