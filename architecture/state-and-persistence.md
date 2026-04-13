# State and Persistence

## 1. Principle

This system has three different persistence scopes. They should not be mixed.

## 2. Scope A: LangGraph Short-Term State

This is thread-scoped state managed by LangGraph checkpoints.

Use it for:

- current messages in the thread,
- current parse result,
- current token resolution result,
- current enrichment snapshot,
- current decision object,
- current execution attempt state,
- current Telegram response draft,
- transient errors and retry metadata.

Do not use it as the permanent ledger of record.

## 3. Scope B: LangGraph Store

This is long-term memory shared across threads.

Use it for small, recallable, cross-session data such as:

- user preferences,
- communication preferences,
- feature flags,
- stable strategy configuration,
- selected trading style (`degen` / `normal` / `safe`),
- resolved global trading parameters,
- chain allowlists,
- tool exposure flags,
- source-level heuristics cache if small.

Do not put full trade history or raw market snapshots here.

## 4. Scope C: Application Persistent Layer

This is the real system of record and should live in PostgreSQL.

Use it for:

- followed sources,
- raw Telegram messages,
- parsed signals,
- token resolution records,
- enrichment snapshots,
- trade decisions,
- execution records,
- active positions,
- closed positions,
- audit events,
- scheduled monitoring jobs,
- idempotency keys,
- error records,
- analytics rollups.

## 5. Thread Design

Recommended thread ids:

- `signal:<signal_id>`
- `position:<position_id>`
- `command:<chat_id>:<message_id>`
- `source-profile:<source_id>:<job_id>`

This enables replay and recovery per business workflow.

## 6. What Belongs in Agent State

Recommended custom agent state fields:

```text
messages
action_type
source_id
signal_id
position_id
raw_message_text
parsed_signal
resolved_asset
wallet_snapshot
market_snapshot
signal_overlay
ta_snapshot
risk_snapshot
decision_draft
policy_gate_result
execution_request
execution_result
telegram_summary
```

## 7. What Belongs in Runtime Context

Runtime context should contain dependencies and stable metadata for the current run:

```text
user_id
bot_id
telegram_chat_id
environment
db_session_factory
okx_service_container
policy_config
clock
logger
```

Runtime context should not contain mutable conversation state.

## 8. What Belongs in the Store

Store namespaces can be designed like:

```text
("users", "preferences")
("users", "strategy_config")
("users", "feature_flags")
("sources", "score_cache")
("system", "chain_policies")
```

Examples:

- per-user default slippage policy
- per-user base style preset
- per-user max trade amount
- per-user lane enablement for major vs regular assets
- allowed chains
- communication style
- source reputation cache

## 9. Business Persistence Tables

Recommended minimum tables:

- `users`
- `wallet_sessions`
- `followed_sources`
- `source_messages`
- `parsed_signal_candidates`
- `asset_resolutions`
- `enrichment_snapshots`
- `trade_decisions`
- `trade_executions`
- `positions`
- `position_events`
- `telegram_notifications`
- `workflow_runs`
- `audit_events`

## 10. Memory Policy By Action

## 10.1 Signal Intake

Short-term state:

- message text
- parse output
- current enrichment
- decision draft

Persistent DB:

- raw message
- parsed signal record
- decision record

Store:

- maybe source scoring hints

## 10.2 Position Monitoring

Short-term state:

- current position snapshot
- market refresh
- exit recommendation

Persistent DB:

- position events
- exit execution record

Store:

- none required by default

## 10.3 User Commands

Short-term state:

- current request context
- response draft

Persistent DB:

- command audit log if needed
- `user_strategy_profiles` updates for `/trade-style`

Store:

- user display preferences
- current strategy profile for `/trade-style`

## 11. Checkpointer Recommendation

For local development:

- `InMemorySaver`

For production-like environments:

- persistent LangGraph checkpointer backed by Postgres

Reason:

- resumable runs,
- replay/debugging,
- safer failure recovery,
- thread-based short-term memory.

## 12. Idempotency Requirements

Execution-sensitive nodes must be idempotent:

- `execute_trade`
- `execute_exit`
- `notify_telegram`

Use persisted idempotency keys such as:

- `signal_id + action_type + version`
- `position_id + exit_trigger + version`

## 13. Recovery Policy

If a run fails:

1. inspect latest checkpoint via thread id
2. inspect workflow run row in DB
3. determine whether execution already happened
4. resume only from the safe next node

The DB remains the source of truth for whether a trade was already submitted.

## 14. What Not To Store in Prompts

Do not dump these directly into every model call:

- full trade history,
- full raw wallet history,
- all Telegram history,
- all holder/trader details,
- full DB objects.

Instead:

- summarize first,
- pass only current action-relevant slices,
- keep prompt context compact.
