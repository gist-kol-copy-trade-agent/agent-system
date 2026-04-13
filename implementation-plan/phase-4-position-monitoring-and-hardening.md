# Phase 4: Position Monitoring and Hardening

## Goal

Close the loop for the PoC by implementing:

- active-position monitoring,
- exit execution,
- reliability hardening,
- observability and demo stability.

## Detailed Plan

## 1. Position Monitoring Scheduler

Implement a scheduler or worker flow that periodically:

- loads active positions
- refreshes market state
- reevaluates exits

## 2. Exit Decision Flow

Implement:

- KOL follow-up message matching to active positions
- scheduled exit reevaluation
- exit agent
- deterministic exit policy gate
- sell execution

## 3. Exit Defaults

Implement fallback behavior using strategy profile defaults:

- stop loss
- take profit
- max holding time

## 4. Reliability Hardening

Implement:

- idempotent execution retries
- safe resume from checkpoints
- dead-letter or failure queue for unrecoverable workflow failures
- better error logging around external adapters

## 5. Observability and Auditability

Implement:

- LangSmith tracing across agents and graphs
- structured workflow logs
- audit event coverage for:
  - settings changes
  - source registration changes
  - trade decisions
  - executions
  - exits

## 6. Demo Stabilization

Implement operational support for demo use:

- fixture or replay mode for demo messages if needed
- clear monitoring dashboards or logs
- deterministic explanation messages for skipped/blocked/executed trades

## Acceptance Criteria

- open positions can be reevaluated on a schedule
- explicit KOL exit messages can trigger exit flow
- fallback TP/SL/time exits work when signal has no explicit exit
- exit trades create execution + position event records
- workflow restart does not create duplicate executions
- failed external integrations can be retried or surfaced cleanly
- tracing/logging is sufficient to debug:
  - why a trade executed
  - why a trade was skipped
  - why a trade was blocked
  - why an exit triggered
- the full PoC demo can show:
  - source registration
  - incoming webhook
  - major lane trade
  - regular lane trade
  - position monitoring or exit behavior

## References

- [../architecture/action-flows.md](../architecture/action-flows.md)
- [../architecture/state-and-persistence.md](../architecture/state-and-persistence.md)
- [../architecture/persistence-schema.md](../architecture/persistence-schema.md)
- [../architecture/policy-spec.md](../architecture/policy-spec.md)
- [../architecture/config-spec.md](../architecture/config-spec.md)
- [../architecture/core-agent-architecture.md](../architecture/core-agent-architecture.md)
