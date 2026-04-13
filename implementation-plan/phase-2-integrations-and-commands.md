# Phase 2: Integrations and Commands

## Goal

Implement the user-facing control plane and external service integration layer.

This phase should produce:

- Telegram command handling,
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

Start with deterministic handlers and add bounded model-assisted parsing only where required.

## 2. `/trade-style` End-to-End Flow

Implement:

- read current profile
- apply preset updates
- parse natural-language overrides
- validate updates
- persist to DB
- mirror into LangGraph store
- return final resolved profile

This is a critical phase deliverable because later trade decisions depend on it.

## 3. Wallet Session Flows

Implement `/start`-related runtime support:

- wallet status lookup
- login flow initiation
- OTP verification handling
- address and balance fetch
- readiness summary

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

- local source creation in pending state
- scraper registration on `/follow`
- scraper unregistration on `/stop`
- final source state transitions

## 7. Command-Side Read Models

Implement enough read-side logic for:

- `/portfolio`
- `/history`
- `/status`

These can start as DB-first views with optional enrichment from wallet and market adapters.

## Acceptance Criteria

- Telegram command router can handle all V1 commands
- `/trade-style` supports:
  - view current settings
  - preset update
  - natural-language override update
- strategy profile changes persist in DB and LangGraph store
- `/follow` triggers scraper registration and stores the subscription mapping
- `/stop` triggers scraper unregistration and deactivates the local source
- webhook endpoint validates auth, deduplicates events, persists messages, and enqueues work
- `/start` can show wallet + strategy readiness state
- command flows have integration tests for success and key failure paths

## References

- [../architecture/telegram-command-contract.md](../architecture/telegram-command-contract.md)
- [../architecture/scraper-integration-contract.md](../architecture/scraper-integration-contract.md)
- [../architecture/user-strategy-profile-schema.md](../architecture/user-strategy-profile-schema.md)
- [../architecture/state-and-persistence.md](../architecture/state-and-persistence.md)
- [../architecture/config-spec.md](../architecture/config-spec.md)
- [../architecture/action-flows.md](../architecture/action-flows.md)
