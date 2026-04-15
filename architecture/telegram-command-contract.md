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

1. invoke `WalletAgent`
2. load `okx-agentic-wallet`
3. check wallet status
4. if not logged in, start login flow
5. if the user provided OTP, verify login
6. fetch wallet balances and addresses
7. check whether a strategy profile exists
8. if no strategy profile exists, guide user toward `/trade-style`
9. return readiness summary

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

- required for `WalletAgent` skill-guided login, verification, and status reads
- deterministic code still owns state persistence and final response rendering

## 5. `/trade-style`

## Goal

View or modify the global trading style and resolved strategy parameters.

## Accepted Forms

```text
/trade-style
/trade-style safe
/trade-style normal
/trade-style degen
confirm
cancel
set max amount per trade to 250
disable regular token trades
set regular token slippage to 3 percent
```

## Behavior

This command is a guided multi-turn setup flow.

### Step 1: Start Setup

If the user sends only:

```text
/trade-style
```

the bot should:

1. load the current profile
2. show the current base style and current resolved profile
3. ask the user to choose one of:
   - `degen`
   - `normal`
   - `safe`
4. create or refresh a pending setup session in `awaiting_base_style`

### Step 2: Style Selection

If the user selects:

```text
degen
normal
safe
```

or sends:

```text
/trade-style degen
/trade-style normal
/trade-style safe
```

the bot should:

1. create a draft profile from the selected preset
2. render the full proposed resolved parameter set
3. ask the user to:
   - reply `confirm` to save, or
   - type what should be changed
4. move the setup session to `awaiting_override_or_confirm`

### Step 3: Override Draft

If the user sends free-form override text while the setup session is pending, the bot should:

1. parse the requested updates into a structured patch
2. deterministically merge the patch into the draft profile
3. validate the merged draft
4. render the updated resolved profile
5. ask again for `confirm` or more changes

### Step 4: Confirm or Cancel

If the user replies:

```text
confirm
```

the bot should:

1. persist the resolved profile
2. clear the pending setup session
3. return the final saved profile

If the user replies:

```text
cancel
```

the bot should:

1. discard the draft setup session
2. leave the existing saved profile unchanged
3. return a cancellation acknowledgement

## Output

Should include:

- current or proposed `base_style`
- resolved draft or final profile
- changed fields when overrides are applied
- a clear prompt for next action:
  - choose style
  - confirm
  - or change parameters

## State Mutation

- updates `user_strategy_profiles` in DB
- updates LangGraph store `("users", "strategy_profile")`
- appends audit record for settings change
- uses a transient setup-session store or DB table while the guided flow is in progress

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
- biggest observed winner
- major-vs-regular asset bias
- granular pattern breakdown
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
2. call `PositionTrackerAgent`
3. load `okx-dex-market`
4. gather:
   - `onchainos market portfolio-recent-pnl`
   - `onchainos market portfolio-token-pnl`
5. merge wallet PnL snapshot with active bot-managed positions
6. render concise summary

## Output

- active positions
- wallet summary
- chain distribution
- headline unrealized state if available

## State Mutation

- none required except optional audit log

## Model Usage

- required for `PositionTrackerAgent` market / PnL gathering
- optional only for additional response summarization beyond the tracked snapshot

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

1. read completed bot-managed trades from DB
2. derive deterministic query window:
   - `/history 7d` => `begin = now - 7d`, `end = now`
   - `/history 30d` => `begin = now - 30d`, `end = now`
   - `/history` => `begin = earliest closed trade timestamp in DB` (fallback `now - 30d`), `end = now`
3. derive deterministic target chains from completed bot-managed trades in DB (deduplicated)
4. call `HistoryAgent`
5. load `okx-dex-market`
6. gather:
   - `onchainos market portfolio-dex-history` per target chain with deterministic `begin/end`
7. merge wallet DEX history with local completed bot-managed trades
8. compute summary stats
9. return compact history report

## Output

- completed trades
- win/loss summary
- source-level summary

## State Mutation

- none required except optional audit log

## Model Usage

- required for `HistoryAgent` DEX history gathering
- optional only for additional summarization beyond the tracked history snapshot

## 10. `/status`

## Goal

Show wallet readiness status only.

## Accepted Forms

```text
/status
```

## Behavior

1. invoke `WalletAgent`
2. load `okx-agentic-wallet`
3. check wallet status
4. return wallet status summary

## Output

- wallet status
- wallet account context (if available)
- wallet addresses (if available)

## State Mutation

- none required except optional audit log

## Model Usage

- required for `WalletAgent` wallet status reads
- deterministic layer only normalizes and returns the wallet payload

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
