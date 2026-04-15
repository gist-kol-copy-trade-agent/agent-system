# Phase 4: Position Monitoring and Hardening

## Goal

Close the first full trading loop by implementing:

- active-position monitoring,
- cron-driven exit evaluation and execution,
- reliability hardening,
- observability and runtime stability.

## Detailed Plan

## 1. Position Monitoring Scheduler and Runtime Boundary

Implement a scheduler, queue, and runtime boundary that:

- periodically loads active positions
- creates one exit-evaluation workflow run per open position
- invokes the exit LangGraph with a deterministic `thread_id`
- separates:
  - scheduler
  - enqueue
  - graph invocation

## 2. Exit Schemas and State

Add code-ready contracts for:

- position monitoring state
- market refresh state
- exit TA snapshot
- trailing state
- exit decision
- exit execution request/result

The exit decision contract should support:

- `hold`
- `exit_hard`
- `exit_trailing_arm`
- `exit_trailing_fire`

## 3. Exit LangGraph

Implement a dedicated LangGraph workflow for scheduled exit reevaluation:

1. load position
2. load strategy profile
3. load position tracking context
4. compute exit TA
5. build exit inputs
6. call exit agent
7. apply deterministic exit policy gate
8. either persist trailing/hold state or execute sell
9. persist result
10. notify Telegram

The graph must not depend on KOL follow-up messages.

## 4. Exit Decision Logic and Defaults

Implement fallback behavior using strategy profile defaults and current position state:

- stop loss
- take profit
- max holding time
- trailing activation
- trailing drawdown

The `Exit Agent` should use market data and settings to decide between:

- `hold`
- `exit_hard`
- `exit_trailing_arm`
- `exit_trailing_fire`

Position market and PnL context should come from a dedicated `PositionTrackerAgent` that uses `okx-dex-market`, especially:

- `onchainos market portfolio-recent-pnl`
- `onchainos market portfolio-token-pnl`
- supporting `market kline` reads for exit TA

## 5. Swap Execution Agent for Exit

Implement bounded sell execution after the exit gate passes:

- reuse the shared `Swap Execution Agent`
- call it with validated sell intent
- load `okx-dex-swap` skill
- let the agent synthesize sell execution request / route details from validated inputs
- invoke sell execution through the execution-agent tool surface
- persist execution and position-close records
- guarantee idempotent behavior on retries

The `Exit Agent` must not call sell execution directly.
The execution agent runs only after the deterministic exit gate has passed.

Implementation order:

1. replace current exit execution runner path with swap-execution-agent path
2. keep idempotency, execution persistence, and position-close persistence in deterministic nodes

## 6. Reliability Hardening

Implement:

- idempotent execution retries
- safe resume from checkpoints
- dead-letter or failure queue for unrecoverable workflow failures
- better error logging around `onchainos` CLI execution and external integrations

## 7. Observability and Auditability

Implement:

- LangSmith tracing across agents and graphs
- structured workflow logs
- audit event coverage for:
  - settings changes
  - source registration changes
  - trade decisions
  - executions
  - exits

## 8. Operational Stabilization

Implement operational support for stable monitored operation:

- fixture or replay mode for controlled message reprocessing if needed
- clear monitoring dashboards or logs
- deterministic explanation messages for skipped/blocked/executed trades and exits

## Acceptance Criteria

- open positions can be reevaluated on a schedule
- each scheduled reevaluation creates or resumes a LangGraph exit workflow
- fallback TP/SL/time exits work when no explicit manual exit exists
- trailing state can be armed and later fired based on configured thresholds
- exit trades create execution + position event records
- exit execution uses a bounded `Swap Execution Agent` after policy approval, not backend-only sell request construction
- workflow restart does not create duplicate executions
- failed external integrations can be retried or surfaced cleanly
- tracing/logging is sufficient to debug:
  - why a trade executed
  - why a trade was skipped
  - why a trade was blocked
  - why an exit triggered
- the full runtime can support:
  - source registration
  - incoming webhook
  - major lane trade
  - regular lane trade
  - scheduled position monitoring and exit behavior

## References

- [../architecture/action-flows.md](../architecture/action-flows.md)
- [../architecture/state-and-persistence.md](../architecture/state-and-persistence.md)
- [../architecture/persistence-schema.md](../architecture/persistence-schema.md)
- [../architecture/policy-spec.md](../architecture/policy-spec.md)
- [../architecture/config-spec.md](../architecture/config-spec.md)
- [../architecture/core-agent-architecture.md](../architecture/core-agent-architecture.md)
