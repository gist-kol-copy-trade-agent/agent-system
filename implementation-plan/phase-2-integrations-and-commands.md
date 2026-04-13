# Phase 2: Integrations and Commands

## Goal

Implement the user-facing control plane and external service integration layer.

This phase should produce:

- Telegram command handling,
- `WalletService` runtime backed by `WalletAgent`,
- `/trade-style` strategy profile flow,
- scraper register/unregister integration,
- scraper webhook intake endpoint,
- strategy profile persistence and retrieval,
- wallet/session readiness command flows.

## Detailed Plan

## 1. Telegram Command Router

Implement routing and handlers for:

- `/start`
- `/trade-style`
- `/follow`
- `/stop`
- `/portfolio`
- `/history`
- `/status`

Wallet-oriented commands should not be treated as plain deterministic handlers.
They should use bounded OKX-skill agents:

- `WalletAgent` for `/start` and `/status`
- `PositionTrackerAgent` for `/portfolio`
- `HistoryAgent` for `/history`

## 2. `/trade-style` End-to-End Flow

Implement:

- guided setup session start
- style selection (`degen` / `normal` / `safe`)
- draft profile proposal rendering
- free-form override parsing
- deterministic merge + validation
- explicit `confirm` / `cancel`
- persist to DB
- mirror into LangGraph store
- return final resolved profile

This is a critical phase deliverable because later trade decisions depend on it.

## 3. Wallet Session Flows

Implement `/start`-related runtime support:

- `WalletService` orchestration
- `WalletAgent` invocation
- `okx-agentic-wallet` skill loading
- wallet status lookup through model tool calls
- login flow initiation through bounded command flow
- OTP verification handling
- address and balance fetch through model tool calls
- readiness summary

The app may still persist normalized wallet state, but the primary interaction path should be skill-guided LLM tool use rather than hardcoded business wrappers.

## 4. Scraper Client

Implement bot -> scraper API calls:

- register source
- unregister source

Requirements:

- request signing or auth headers if configured
- response normalization
- idempotent local updates
- failure recording

## 5. Webhook Intake

Implement scraper -> bot webhook endpoint:

- signature verification
- timestamp freshness check
- payload validation
- idempotency on event id
- raw event persistence
- message persistence
- enqueue signal intake workflow

Do not perform full trade analysis inline in the webhook request path.

## 6. Follow/Stop Source Flows

Implement:

- local source creation in profiling-pending state
- scraper historical fetch request on `/follow`
- async profiling callback intake
- LLM call extraction over 7-day samples
- retrospective 1-day market evaluation for extracted calls
- channel profile summary and conviction suggestion
- explicit user confirmation before live registration
- scraper registration only after user confirms follow
- scraper unregistration on `/stop`
- final source state transitions

## 7. Command-Side Read Models

Implement enough read-side logic for:

- `/portfolio`
- `/history`
- `/status`

These should use:

- `WalletAgent` + `okx-agentic-wallet` for wallet-native readiness data
- `PositionTrackerAgent` + `okx-dex-market` for portfolio/PnL tracking
- `HistoryAgent` + `okx-dex-market` for DEX history tracking
- DB-first views only for local history and durable app records

## Acceptance Criteria

- Telegram command router can handle all V1 commands
- `/trade-style` supports:
  - guided setup start
  - preset selection
  - draft proposal rendering
  - natural-language override update
  - explicit confirm / cancel
- strategy profile changes persist in DB and LangGraph store
- `/follow` triggers scraper registration and stores the subscription mapping
- `/follow` can trigger historical profiling before registration
- profiling result is delivered asynchronously and converted into a user-facing channel analysis
- live channel registration happens only after user confirmation
- `/stop` triggers scraper unregistration and deactivates the local source
- webhook endpoint validates auth, deduplicates events, persists messages, and enqueues work
- `/start` can show wallet + strategy readiness state through `WalletAgent`
- `/status` uses `WalletAgent` with `okx-agentic-wallet` for wallet readiness data
- `/history` uses `HistoryAgent` with `okx-dex-market` plus local completed-trade records
- `/portfolio` uses `PositionTrackerAgent` with `okx-dex-market` plus local bot-position records
- command flows have integration tests for success and key failure paths

## References

- [../architecture/telegram-command-contract.md](../architecture/telegram-command-contract.md)
- [../architecture/scraper-integration-contract.md](../architecture/scraper-integration-contract.md)
- [../architecture/user-strategy-profile-schema.md](../architecture/user-strategy-profile-schema.md)
- [../architecture/state-and-persistence.md](../architecture/state-and-persistence.md)
- [../architecture/config-spec.md](../architecture/config-spec.md)
- [../architecture/action-flows.md](../architecture/action-flows.md)
