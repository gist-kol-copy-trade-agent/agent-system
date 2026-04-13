# Action Flows

## Purpose

This document defines, for each major bot action:

- whether the model is called,
- which tools are available,
- which steps are deterministic,
- what gets persisted.

## 1. New Telegram Signal

## 1.1 Goal

Turn an inbound Telegram message into one of:

- ignored event,
- tracked but not traded event,
- executed buy trade.

## 1.2 Flow

### Step 1: Ingest
Deterministic.

Inputs:

- source channel metadata
- Telegram message payload
- receive timestamp

Persist:

- raw message
- source id
- signal ingestion record

### Step 2: Parse Signal
Model call: yes

Agent:

- `Parsing Agent`

Tools exposed:

- `search_token_candidates`
- `get_token_metadata` (optional)

Expected output:

- structured parse result
- `is_trade_call`
- extracted symbol / CA / chain hints

Persist:

- parse result
- parse confidence

### Step 3: Parse Validation
Deterministic.

Rules:

- if not a trade call -> stop
- if no token clue at all -> stop
- if multiple unresolved token candidates remain -> stop

Persist:

- skip reason if stopped

### Step 4: Classify Asset Lane
Deterministic.

Rules:

- `BTC`, `ETH`, `SOL` -> `major asset lane`
- everything else -> `regular token lane`

Persist:

- `asset_lane`
- normalized asset symbol
- target execution chain

### Step 5: Resolve Target Asset
Deterministic, tool-driven.

Model call: no

Tools:

- `resolve_token_identity`
- `get_token_market_snapshot`

Persist:

- For major assets:
  - approved X Layer trading representation
  - target execution chain = `xlayer`
- For regular tokens:
  - resolved chain
  - contract address
  - decimals
  - market metadata snapshot

### Step 6: Load Wallet Context
Deterministic.

Model call: no

Tools:

- `get_wallet_context`

Rules:

- if not logged in -> stop
- if no funds on target execution chain -> stop

Persist:

- wallet readiness snapshot

### Step 7: Enrichment
Mostly deterministic.

Model call: no

Tools:

- `get_token_market_snapshot`
- `get_token_risk`
- `get_signal_overlay`
- `get_major_asset_execution_context`
- `compute_ta_score`
- `build_trade_sizing_inputs`

Persist:

- enrichment snapshot
- TA snapshot
- risk snapshot

Lane behavior:

- major asset lane:
  - use price, K-line, quote readiness, X Layer wallet readiness
  - skip regular-token risk research
- regular token lane:
  - use full enrichment and token-risk path

### Step 8: Decision Synthesis
Model call: yes

Agent:

- `Decision Agent`

Tools exposed:

- `get_wallet_context`
- `get_token_market_snapshot`
- `get_token_risk`
- `get_signal_overlay`
- `get_major_asset_execution_context`
- `compute_ta_score`
- `build_trade_sizing_inputs`

Tools not exposed:

- execution tools

Expected output:

- `execute | skip | block`
- rationale
- recommended sizing factor

Persist:

- structured decision object

### Step 9: Policy Gate
Deterministic.

Model call: no

Checks:

- token exact match exists when required by lane
- risk scan passed for regular tokens
- quote exists
- price impact within cap
- amount within policy
- active positions within cap
- chain exposure within cap

Persist:

- policy decision
- failure reason if blocked

### Step 10: Execute Buy
Deterministic.

Model call: no

Tools:

- `execute_swap_buy`

Persist:

- tx hashes
- execution status
- quote context

### Step 11: Notify
Optional model call: no by default

Use deterministic template first.
If needed, a small summary-generation model call can rewrite the explanation for Telegram.

Persist:

- outbound Telegram notification record

## 2. Exit Trigger From KOL Follow-Up Message

## 2.1 Goal

Exit an active position when a new message strongly implies an exit.

## 2.2 Flow

### Step 1: Ingest Follow-Up Message
Deterministic.

Persist raw message and source mapping.

### Step 2: Parse Exit Intent
Model call: yes

Agent:

- `Parsing Agent`

Output:

- `message_type`
- `is_exit_signal`
- referenced token / position hints

### Step 3: Match To Active Position
Deterministic.

Use local DB to match:

- source channel
- token
- chain
- active position id

If no active position matches, stop.

### Step 4: Refresh Exit Context
Deterministic.

Tools:

- `get_position_snapshot`
- `get_token_market_snapshot`
- `compute_exit_ta_score`

### Step 5: Exit Decision
Model call: yes

Agent:

- `Exit Agent`

Tools exposed:

- `get_position_snapshot`
- `get_token_market_snapshot`
- `compute_exit_ta_score`

### Step 6: Exit Policy Gate
Deterministic.

Checks:

- position still open
- liquidity still available
- quote exists
- sell route acceptable

### Step 7: Execute Exit
Deterministic.

Tools:

- `execute_swap_sell`

Persist:

- exit tx hash
- realized output
- position closed state

## 3. Exit Trigger From Price / TA / Risk Rule

## 3.1 Goal

Exit without a new Telegram message when monitoring rules trigger.

## 3.2 Flow

### Step 1: Scheduled Position Poll
Deterministic.

Load active positions needing refresh.

### Step 2: Refresh Data
Deterministic.

Tools:

- `get_token_market_snapshot`
- `compute_exit_ta_score`

### Step 3: Determine Trigger Type
Deterministic first.

Rules:

- static TP hit
- static SL hit
- trailing stop broken
- max holding time exceeded
- risk deterioration

Only if signal is ambiguous should the system call the `Exit Agent`.

### Step 4: Execute Exit
Deterministic.

Tools:

- `execute_swap_sell`

## 4. `/start`

Mostly deterministic.

Flow:

1. check wallet status
2. initiate login if needed
3. fetch balance
4. fetch addresses
5. persist readiness state
6. respond to Telegram

Tools:

- `wallet_status`
- `wallet_login`
- `wallet_verify`
- `wallet_balance`
- `wallet_addresses`

## 5. `/trade-style`

Mostly deterministic with one optional bounded model step for natural-language parameter updates.

### Goal

Let the user:

- inspect current strategy profile,
- switch base style to `degen`, `normal`, or `safe`,
- override individual parameters,
- persist the resolved global strategy settings.

### Flow

1. load current strategy profile from store / DB
2. if the command is only `/trade-style`, return:
   - current base style
   - current resolved parameters
   - suggested preset alternatives
3. if the user specifies a preset, apply preset defaults
4. if the user specifies natural-language overrides, parse them into structured updates
5. validate the merged profile
6. persist updated profile to DB and LangGraph store
7. return the final resolved profile to Telegram

Model call:

- optional, only for parsing free-form parameter overrides into structured update intents

Deterministic components:

- preset application
- schema validation
- persistence
- final rendering

Primary persistence targets:

- `user_strategy_profiles` table
- LangGraph store namespace `(\"users\", \"strategy_profile\")`

## 6. `/follow`

Mostly deterministic with optional model call for channel normalization.

Flow:

1. validate source link
2. persist source
3. optionally fetch recent sample messages
4. optionally run heuristic cold-start profiling
5. respond with follow status

Model call:

- optional for cold-start message classification

## 7. `/portfolio`

Deterministic.

Flow:

1. load internal active positions
2. fetch current wallet balance snapshot
3. optionally fetch portfolio analytics
4. render Telegram summary

Tools:

- `get_wallet_context`
- `get_portfolio_analytics`

## 8. `/history`

Deterministic.

Primary source:

- application DB

Optional enrichment:

- OKX market portfolio history tools

## 9. Tool Calling Policy Summary

Expose tools to the model only when needed.

### Allowed direct model tools

- read-only lookup tools
- scoring helper tools
- summarization helper tools

The exact set should be filtered by asset lane before each agent call.

### Not allowed as general model tools

- swap execution tools
- raw contract call tools
- gateway broadcast tools
- database mutation tools that change trade state directly

These actions should remain in deterministic graph nodes.
