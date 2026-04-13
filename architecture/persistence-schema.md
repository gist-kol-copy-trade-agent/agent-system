# Persistence Schema

## 1. Purpose

This document defines the recommended PostgreSQL schema shape for the PoC/V1 bot.

It is not a migration file. It is the implementation-facing persistence contract.

## 2. Design Principles

- PostgreSQL is the system of record.
- LangGraph checkpoints are not the business ledger.
- Every execution-sensitive object needs an idempotency key.
- Keep raw payloads and normalized domain records separate.

## 3. Core Tables

## 3.1 `users`

Columns:

- `id` PK
- `telegram_user_id` unique
- `created_at`
- `updated_at`

## 3.2 `wallet_sessions`

Columns:

- `id` PK
- `user_id` FK -> `users.id`
- `account_id`
- `account_name`
- `login_type`
- `logged_in`
- `wallet_evm_address`
- `wallet_sol_address`
- `wallet_xlayer_address`
- `policy_json` jsonb
- `last_synced_at`
- `created_at`
- `updated_at`

Indexes:

- `(user_id)`

## 3.3 `user_strategy_profiles`

Columns:

- `id` PK
- `user_id` FK -> `users.id`
- `base_style`
- `profile_json` jsonb
- `version`
- `updated_by`
- `created_at`
- `updated_at`

Constraints:

- unique `(user_id)`

## 3.4 `followed_sources`

Columns:

- `id` PK
- `user_id` FK -> `users.id`
- `source_id` unique
- `channel_name`
- `channel_url`
- `scraper_subscription_id`
- `status`
- `registered_at`
- `unsubscribed_at`
- `created_at`
- `updated_at`

Indexes:

- `(user_id, status)`
- `(channel_name)`

## 3.5 `source_messages`

Columns:

- `id` PK
- `source_id` FK -> `followed_sources.source_id`
- `event_id`
- `message_id`
- `message_timestamp`
- `message_text`
- `message_url`
- `raw_payload_json` jsonb
- `received_at`
- `created_at`

Constraints:

- unique `(event_id)`
- unique `(source_id, message_id, message_timestamp)`

Indexes:

- `(source_id, message_timestamp desc)`

## 3.6 `parsed_signal_candidates`

Columns:

- `id` PK
- `signal_id` unique
- `source_message_id` FK -> `source_messages.id`
- `source_id`
- `message_type`
- `is_actionable`
- `parsed_json` jsonb
- `parse_confidence`
- `created_at`

Indexes:

- `(source_id, created_at desc)`
- `(is_actionable, created_at desc)`

## 3.7 `asset_resolutions`

Columns:

- `id` PK
- `signal_id` FK -> `parsed_signal_candidates.signal_id`
- `asset_lane`
- `normalized_symbol`
- `target_execution_chain`
- `resolved_signal_chain`
- `token_contract_address`
- `resolution_json` jsonb
- `created_at`

Indexes:

- `(signal_id)`
- `(asset_lane, normalized_symbol)`

## 3.8 `enrichment_snapshots`

Columns:

- `id` PK
- `signal_id` FK -> `parsed_signal_candidates.signal_id`
- `wallet_snapshot_json` jsonb
- `market_snapshot_json` jsonb
- `risk_snapshot_json` jsonb
- `signal_overlay_json` jsonb
- `ta_snapshot_json` jsonb
- `strategy_profile_version`
- `created_at`

Indexes:

- `(signal_id)`

## 3.9 `trade_decisions`

Columns:

- `id` PK
- `signal_id` FK -> `parsed_signal_candidates.signal_id`
- `source_id`
- `asset_lane`
- `decision`
- `decision_reason_code`
- `recommended_amount_usd`
- `capped_amount_usd`
- `decision_json` jsonb
- `created_at`

Indexes:

- `(signal_id)`
- `(source_id, created_at desc)`
- `(decision, created_at desc)`

## 3.10 `trade_executions`

Columns:

- `id` PK
- `execution_id` unique
- `signal_id` FK -> `parsed_signal_candidates.signal_id`
- `position_id`
- `asset_lane`
- `side`
- `chain`
- `wallet_address`
- `from_token`
- `to_token`
- `requested_amount`
- `approve_tx_hash`
- `swap_tx_hash`
- `success`
- `error_code`
- `error_message`
- `idempotency_key`
- `execution_json` jsonb
- `created_at`

Constraints:

- unique `(idempotency_key)`

Indexes:

- `(signal_id)`
- `(position_id)`
- `(swap_tx_hash)`

## 3.11 `positions`

Columns:

- `id` PK
- `position_id` unique
- `user_id` FK -> `users.id`
- `source_id`
- `asset_lane`
- `chain`
- `symbol`
- `token_contract_address`
- `wallet_address`
- `entry_signal_id`
- `entry_execution_id`
- `entry_price_usd`
- `entry_amount_usd`
- `status`
- `opened_at`
- `closed_at`
- `created_at`
- `updated_at`

Indexes:

- `(user_id, status)`
- `(source_id, status)`
- `(chain, status)`

## 3.12 `position_events`

Columns:

- `id` PK
- `position_id` FK -> `positions.position_id`
- `event_type`
- `event_reason_code`
- `event_json` jsonb
- `created_at`

Indexes:

- `(position_id, created_at desc)`

## 3.13 `telegram_notifications`

Columns:

- `id` PK
- `user_id` FK -> `users.id`
- `chat_id`
- `related_signal_id`
- `related_position_id`
- `notification_type`
- `message_text`
- `send_status`
- `sent_at`
- `created_at`

Indexes:

- `(user_id, created_at desc)`
- `(related_signal_id)`
- `(related_position_id)`

## 3.14 `workflow_runs`

Columns:

- `id` PK
- `thread_id` unique
- `workflow_type`
- `related_signal_id`
- `related_position_id`
- `status`
- `last_node`
- `checkpoint_id`
- `run_metadata_json` jsonb
- `created_at`
- `updated_at`

Indexes:

- `(workflow_type, status)`
- `(related_signal_id)`
- `(related_position_id)`

## 3.15 `audit_events`

Columns:

- `id` PK
- `user_id`
- `event_type`
- `entity_type`
- `entity_id`
- `event_json` jsonb
- `created_at`

Indexes:

- `(user_id, created_at desc)`
- `(entity_type, entity_id)`

## 4. Enum Recommendations

Recommended enum-like values:

- `followed_sources.status`: `pending`, `active`, `inactive`, `error`
- `positions.status`: `open`, `closing`, `closed`, `failed`
- `trade_decisions.decision`: `execute`, `skip`, `block`
- `trade_executions.side`: `buy`, `sell`
- `workflow_runs.status`: `pending`, `running`, `completed`, `failed`, `interrupted`

## 5. Idempotency Keys

Recommended patterns:

- signal execution:
  - `signal:{signal_id}:buy:v1`
- position exit:
  - `position:{position_id}:exit:{trigger_code}:v1`
- scraper event:
  - use raw `event_id`

## 6. Raw JSON Strategy

Store normalized first-class columns for key query dimensions, plus full JSON for evolution safety.

Good candidates for first-class columns:

- decision
- chain
- asset lane
- symbol
- tx hash
- status

Use JSONB for:

- raw external payloads
- model structured outputs
- enrichment snapshots
- audit detail

## 7. Required Foreign-Key Integrity

At minimum, enforce:

- strategy profile -> user
- wallet session -> user
- followed source -> user
- source message -> source
- parsed signal -> source message
- asset resolution -> signal
- enrichment snapshot -> signal
- trade decision -> signal
- position event -> position

Where looser coupling is needed, store both FK and denormalized business ids.

## 8. Minimum Query Patterns To Support

The schema should make these queries easy:

- latest active positions for user
- latest messages for a source
- latest decision/execution for a signal
- current strategy profile for user
- source performance by channel
- recent failed executions
- recent scraper webhook failures

## 9. Migration Priority

If implementation starts incrementally, create tables in this order:

1. `users`
2. `wallet_sessions`
3. `user_strategy_profiles`
4. `followed_sources`
5. `source_messages`
6. `parsed_signal_candidates`
7. `asset_resolutions`
8. `enrichment_snapshots`
9. `trade_decisions`
10. `trade_executions`
11. `positions`
12. `position_events`
13. `telegram_notifications`
14. `workflow_runs`
15. `audit_events`
