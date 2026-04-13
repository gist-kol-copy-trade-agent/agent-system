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

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

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

- deterministic app-side resolution using parse output
- optional read-only `onchainos` lookup outside the model when needed for exact normalization

Persist:

- For major assets:
  - approved X Layer trading representation
  - target execution chain = `xlayer`
- For regular tokens:
  - resolved chain
  - contract address
  - decimals
  - market metadata snapshot

### Step 6: Enrichment
Model call: yes

Agent:

- `Enrichment Agent`

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Expected output:

- wallet snapshot
- market snapshot
- risk snapshot
- optional signal overlay / quote context

Persist:

- enrichment snapshot

Lane behavior:

- major asset lane:
  - use price, K-line, quote readiness, X Layer wallet readiness
  - skip regular-token risk research
- regular token lane:
  - use full enrichment and token-risk path

### Step 7: Compute TA
Deterministic.

Model call: no

Tools:

- `compute_ta_score`

Persist:

- TA snapshot

### Step 8: Decision Synthesis
Model call: yes

Agent:

- `Decision Agent`

Tools exposed:

- none by default

Tools not exposed:

- OKX read tools
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
Model call: yes, but only after deterministic policy approval.

Agent:

- `Swap Execution Agent`

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- restricted mutating swap execution tool

Required skill:

- `okx-dex-swap`

Rules:

- input to this step must already be policy-approved
- the execution agent may plan route and execute swap, but may not change trade intent or bypass policy
- idempotency and persistence remain outside the agent

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

## 3. Wallet / Balance Commands

## 3.1 Goal

Handle wallet-oriented Telegram commands using OKX skill-guided model reasoning rather than deterministic business wrappers.

Covered commands:

- `/start`
- `/status`
- `/portfolio`
- `/history`

## 3.2 Flow

### Step 1: Ingest Command
Deterministic.

Persist raw command event if needed.

## 4. Follow Channel

## 4.1 Goal

Analyze a Telegram source before enabling live follow.

The user should receive:

- a cold-start profile based on the last 7 days of messages,
- a suggested conviction level for the source,
- a confirmation prompt asking whether the bot should follow the channel.

Only after user confirmation should the bot register the channel with the scraper.

## 4.2 Flow

### Step 1: Validate Source Input
Deterministic.

Inputs:

- `/follow <channel_link_or_name>`

Rules:

- validate basic Telegram link / username format
- normalize source identifier
- reject obviously malformed inputs early

Persist:

- source record in `profiling_pending` state

### Step 2: Request Historical Messages
Deterministic.

Model call: no

Action:

- call scraper historical fetch API for the most recent 7 days

Persist:

- profiling request id
- fetch status

### Step 3: Receive Historical Samples
Deterministic intake, async workflow handoff.

Model call: no

Inputs:

- historical message callback from scraper

Persist:

- sampled messages
- profiling job record

### Step 4: Extract Trade Calls from Historical Messages
Model call: yes

Agent:

- `Parsing Agent` or a dedicated `Follow Profiling Agent`

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Goal:

- identify messages that are real trade calls
- extract token clues and timestamps from historical samples

Persist:

- extracted historical calls
- extraction confidence

### Step 5: Evaluate Post-Call Market Outcome
Mostly deterministic.

Model call: no by default

Tools:

- `okx-dex-market`
- `onchainos market kline`

Method:

- for each extracted call, estimate call-time price
- compare with market behavior within the following 24 hours
- derive simple retrospective metrics

Persist:

- per-call evaluation
- aggregate metrics

### Step 6: Profile Channel Quality
Model call: yes

Agent:

- `Follow Profiling Agent`

Tools exposed:

- none by default beyond provided profiling inputs

Expected output:

- channel summary
- suggested conviction
- major-vs-regular asset bias
- note on confidence / limitations

Persist:

- channel profiling summary

### Step 7: Ask User for Confirmation
Deterministic.

Output to user:

- sample size
- extracted call count
- estimated win-rate or 1-day follow-through
- suggested conviction
- explicit question: follow this channel or not

Persist:

- follow confirmation pending state

### Step 8: Register Channel After Confirmation
Deterministic.

Model call: no

Action:

- call scraper `POST /register/channel_name`

Persist:

- scraper subscription id
- source state = `active`

### Step 9: Final Response
Deterministic.

Output:

- channel active status
- normalized source id
- suggested conviction used during decision

### Step 2: Interpret Wallet Intent
Model call: yes

Agent:

- `Wallet / Command Agent`

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Required skill:

- `okx-agentic-wallet`

Optional supporting skill:

- `okx-dex-market` for portfolio or PnL-related follow-up

Expected output:

- resolved wallet intent
- requested command mode
- any required parameters still missing

### Step 3: Execute Skill-Guided Read Path
Model call: yes

Agent:

- `Wallet / Command Agent`

Behavior:

- load `okx-agentic-wallet`
- issue read-only `onchainos` calls for status, balance, addresses, or history
- optionally use `okx-dex-market` for portfolio market/PnL context

Persist:

- wallet readiness snapshot when relevant
- command response audit event

### Step 4: Deterministic Post-Processing
Deterministic.

Rules:

- normalize returned payloads for Telegram presentation
- store any durable wallet session metadata needed by the app
- do not let the model mutate trading state directly

## 2. Scheduled Exit Evaluation

## 2.1 Goal

Reevaluate an active position on a schedule and decide whether to:

- hold,
- arm trailing logic,
- fire a trailing exit,
- hard exit now.

## 2.2 Flow

### Step 1: Scheduled Position Poll
Deterministic.

Load active positions that are due for reevaluation.

Persist:

- scheduler tick or cycle id
- position ids selected for reevaluation

### Step 2: Load Position and Strategy Context
Deterministic.

Load:

- position snapshot
- trailing state
- user strategy profile

### Step 3: Refresh Exit Context
Deterministic.

Tools:

- `get_position_snapshot`
- `get_token_market_snapshot`
- `compute_exit_ta_score`

Persist:

- market refresh snapshot
- exit TA snapshot

### Step 4: Exit Decision
Model call: yes

Agent:

- `Exit Agent`

Tools exposed:

- `get_position_snapshot`
- `get_token_market_snapshot`
- `compute_exit_ta_score`

Expected output:

- `hold | exit_hard | exit_trailing_arm | exit_trailing_fire`
- rationale
- confidence
- suggested sell fraction if partial exit is ever enabled later

### Step 5: Exit Policy Gate
Deterministic.

Checks:

- position still open
- liquidity still available
- quote exists
- sell route acceptable
- trailing state transition is valid
- hard stop / TP / time rule is compatible with policy

Persist:

- exit policy result
- failure reasons if blocked

### Step 6: Persist Hold or Trailing Update
Deterministic.

If result is:

- `hold`, persist monitoring outcome only
- `exit_trailing_arm`, persist updated trailing state only

### Step 7: Execute Exit
Model call: yes, but only after deterministic exit policy approval.

Agent:

- `Swap Execution Agent`

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- restricted mutating swap execution tool

Required skill:

- `okx-dex-swap`

Rules:

- execution agent receives validated sell intent only
- it may synthesize route details and call sell execution
- it may not reopen policy decisions or alter exit intent
- idempotency and persistence remain deterministic outside the agent

Persist:

- exit tx hash
- realized output
- position closed state

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
