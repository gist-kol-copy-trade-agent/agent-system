# Telegram Command Contract

## 1. Purpose

This document defines the Telegram command surface for the PoC/V1 bot.

It specifies:

- supported commands,
- accepted input patterns,
- expected outputs,
- state mutations,
- whether the flow is deterministic or model-assisted.

## 2. Command Set

The minimum command set is:

- `/start`
- `/trade-style`
- `/follow`
- `/stop`
- `/portfolio`
- `/history`
- `/status`

## 3. General Command Rules

- Commands should be idempotent when possible.
- Command responses should be concise and operational.
- Commands that mutate durable state must return the resolved final state, not only an acknowledgement.
- When a command supports natural-language arguments, the parsing step may be model-assisted, but validation and persistence must be deterministic.

## 4. `/start`

## Goal

Initialize the user session and bootstrap wallet + strategy readiness.

## Accepted Forms

```text
/start
```

## Behavior

1. check wallet status
2. if not logged in, start login flow
3. fetch wallet balances and addresses
4. check whether a strategy profile exists
5. if no strategy profile exists, guide user toward `/trade-style`
6. return readiness summary

## Output

Should include:

- wallet login status
- active account
- high-level balance snapshot
- whether strategy profile exists
- suggested next step

## State Mutation

- may create or update wallet session state
- may create onboarding audit records

## Model Usage

- not required by default

## 5. `/trade-style`

## Goal

View or modify the global trading style and resolved strategy parameters.

## Accepted Forms

```text
/trade-style
/trade-style safe
/trade-style normal
/trade-style degen
/trade-style set max amount per trade to 250
/trade-style disable regular token trades
/trade-style set regular token slippage to 3 percent
```

## Behavior

### Read Mode

If the user sends only:

```text
/trade-style
```

the bot should return:

- current base style
- current resolved parameter set
- short explanation of what the style means
- suggested preset alternatives

### Preset Update Mode

If the user sends:

```text
/trade-style safe
/trade-style normal
/trade-style degen
```

the bot should:

1. load current profile
2. apply preset defaults
3. preserve only fields that product rules say should remain user-controlled, if any
4. validate final profile
5. persist final profile
6. return the resolved profile

### Override Update Mode

If the user sends natural-language parameter changes, the bot should:

1. parse the requested updates
2. map them into structured fields
3. validate values
4. merge into current profile
5. persist final profile
6. return changed fields and the updated resolved profile

## Output

Should include:

- current or updated `base_style`
- changed fields
- final resolved profile
- note that the profile will be used globally for future trade decisions

## State Mutation

- updates `user_strategy_profiles` in DB
- updates LangGraph store `("users", "strategy_profile")`
- appends audit record for settings change

## Model Usage

- optional, only for parsing free-form overrides
- never for schema validation

## 6. `/follow`

## Goal

Register a Telegram source for monitoring.

## Accepted Forms

```text
/follow <channel_link>
```

## Behavior

1. validate source input
2. normalize channel identifier
3. create or update local source in `profiling_pending` state
4. call scraper historical fetch API for the most recent 7 days
5. persist profiling request state
6. asynchronously receive sampled messages from scraper
7. run LLM-based call extraction on sampled messages
8. use `okx-dex-market` / `onchainos market kline` to evaluate price behavior within 1 day after each call
9. build a channel profile and suggested conviction level
10. ask user whether they want to follow the channel
11. only after confirmation, call scraper `POST /register/channel_name`
12. persist scraper registration result
13. return final source status

## Output

Phase 1 response:

- source normalized
- profiling started / pending status

Phase 2 response after profiling:

- sample size
- extracted call count
- retrospective quality summary
- suggested conviction
- follow confirmation prompt

Phase 3 response after user confirms:

- source registered status
- normalized source id
- suggested conviction snapshot

## State Mutation

- creates or updates `followed_sources`
- stores profiling request state and summary
- stores `scraper_subscription_id` only after registration succeeds

## Model Usage

- required for historical call extraction
- recommended for final channel profiling summary
- not required for final scraper registration once the user confirms

## 7. `/stop`

## Goal

Pause monitoring for a followed source.

## Accepted Forms

```text
/stop <channel_id_or_link>
```

## Behavior

1. resolve source
2. call scraper `POST /unregister/channel_name`
3. mark source inactive
4. return final source state

## Output

- source identifier
- new status

## State Mutation

- updates `followed_sources`

## Model Usage

- not required

## 8. `/portfolio`

## Goal

Show current holdings and active bot-managed positions.

## Accepted Forms

```text
/portfolio
```

## Behavior

1. load active positions from DB
2. fetch wallet balance snapshot
3. optionally fetch portfolio analytics
4. render concise summary

## Output

- active positions
- wallet summary
- chain distribution
- headline unrealized state if available

## State Mutation

- none required except optional audit log

## Model Usage

- optional only for response summarization

## 9. `/history`

## Goal

Show completed trade history and source-level performance summary.

## Accepted Forms

```text
/history
/history 7d
/history 30d
```

## Behavior

1. read trade history from DB
2. apply optional time filter
3. compute summary stats
4. return compact history report

## Output

- completed trades
- win/loss summary
- source-level summary

## State Mutation

- none required except optional audit log

## Model Usage

- optional only for summarization

## 10. `/status`

## Goal

Show bot readiness and operating state.

## Accepted Forms

```text
/status
```

## Behavior

1. check wallet status
2. check strategy profile existence
3. count followed sources
4. count active positions
5. return system summary

## Output

- wallet status
- operating mode
- strategy profile status
- followed source count
- active position count

## State Mutation

- none required except optional audit log

## Model Usage

- not required

## 11. Suggested Response Style

Command responses should prefer:

- current state,
- what changed,
- what happens next.

Example for `/trade-style`:

```text
Trading style updated: normal
Major asset lane: enabled
Regular token lane: enabled
Max amount per trade: 500 USD
Regular token max amount: 200 USD
Regular token min liquidity: 50,000 USD
These settings will apply to all future signal decisions.
```

## 12. Validation Notes

- `/trade-style` must validate against the strategy profile schema
- `/follow` must reject malformed or duplicate sources
- `/stop` must resolve exactly one source
- `/portfolio`, `/history`, and `/status` must still work even if the wallet is not ready, but should reflect degraded status clearly
