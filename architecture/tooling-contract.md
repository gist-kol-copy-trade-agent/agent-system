# Tooling Contract

## 1. Purpose

This document defines the tool surface the LangChain agents should see.

The integration pattern is `skill-first`, not `adapter-first`.

That means:

- the agent loads OKX OnchainOS skills as prompt specializations,
- the agent uses a small generic `onchainos` command execution tool when it needs live OKX-covered data,
- the application only implements custom tools for capabilities not covered by OnchainOS, such as TA and sizing math.

The agents should not depend on a large set of business-specific OKX adapter wrappers like `get_wallet_context` or `get_token_risk` as their primary surface.
Those wrappers may still exist internally for deterministic nodes, but they are not the preferred model-facing pattern.

The tool layer must support two product lanes:

- `major asset lane` for `BTC/ETH/SOL` on `X Layer`
- `regular token lane` for all other tradable assets on the resolved signal chain

## 2. Tool Categories

## 2.1 Skill Tools

Prompt-driven specialization tools.

Examples:

- `load_okx_skill`
- `load_okx_skill_reference`

## 2.2 Read / Execution-Boundary Tools

Safe tools that execute read-only `onchainos` commands or fetch internal state.

Examples:

- `run_onchainos_readonly`
- `get_position_snapshot`

## 2.3 Scoring Tools

Pure functions or read-heavy helpers.

Examples:

- `compute_ta_score`
- `compute_exit_ta_score`
- `build_trade_sizing_inputs`
- `summarize_risk_signals`

## 2.4 Policy Tools

Deterministic business-rule evaluation.

Examples:

- `evaluate_trade_policy_gate`
- `evaluate_exit_policy_gate`

These usually should not be model-facing unless the model needs to inspect the result only.

## 2.5 Execution Tools

Sensitive side-effect tools.

Examples:

- `execute_swap_buy`
- `execute_swap_sell`
- `wallet_login`
- `wallet_verify`

These should not be generally exposed to decision agents.

## 3. Recommended Tool List

## 3.1 Parsing Agent Tools

### `load_okx_skill`
Purpose:

- load a full OKX skill prompt on demand

Examples:

- `okx-dex-token`
- `okx-dex-market`
- `okx-security`
- `okx-agentic-wallet`

### `load_okx_skill_reference`
Purpose:

- load a reference file mentioned by a selected skill

Examples:

- `references/cli-reference.md`
- `references/risk-token-detection.md`
- `_shared/chain-support.md`

### `run_onchainos_readonly`
Purpose:

- execute a read-only `onchainos` command after the agent has loaded the relevant skill instructions

Rules:

- only allow read-only commands for model-facing use
- write / side-effect commands stay outside unrestricted agent control
- the tool should return parsed JSON or structured text payloads

## 3.2 Decision Agent Tools

### `run_onchainos_readonly`
This is the main OKX-facing tool for the decision agent.

Typical commands:

- `onchainos wallet status`
- `onchainos wallet balance --chain <chain>`
- `onchainos wallet addresses --chain <chain>`
- `onchainos market price --address <address>`
- `onchainos market kline --address <address>`
- `onchainos token price-info --address <address>`
- `onchainos security token-scan ...`
- `onchainos token advanced-info --address <address>`
- `onchainos swap quote ...`
- `onchainos signal list`

The relevant skill prompt must be loaded first so the model knows the exact command semantics and safety rules.

### `compute_ta_score`
Pure application tool.

Inputs:

- recent OHLCV
- call reference price
- current price
- liquidity / volume thresholds

Returns:

- TA score
- rule breakdown
- anti-FOMO result

### `build_trade_sizing_inputs`
Pure application tool.

Inputs:

- wallet balance
- source score
- token risk score
- TA score
- policy limits
- asset lane

Returns:

- proposed amount
- capped amount
- sizing explanation

## 3.3 Exit Agent Tools

### `get_position_snapshot`
Reads from application DB.

Returns:

- current position state
- cost basis
- size
- chain
- token

### `compute_exit_ta_score`
Pure application tool.

Inputs:

- current OHLCV
- position basis
- stop / TP configuration

Returns:

- exit signal breakdown

## 3.4 Wallet / Command Agent Tools

### `load_okx_skill`
Primary wallet command skill:

- `okx-agentic-wallet`

Optional portfolio support skill:

- `okx-dex-market`

### `load_okx_skill_reference`
Use for wallet-skill references such as:

- `references/cli-reference.md`
- `references/new-user-guide.md`
- `_shared/chain-support.md`

### `run_onchainos_readonly`
This is the primary wallet data path for model-assisted command handling.

Typical commands:

- `onchainos wallet status`
- `onchainos wallet balance`
- `onchainos wallet balance --chain <chain>`
- `onchainos wallet addresses --chain <chain>`
- `onchainos wallet history`
- `onchainos wallet history --tx-hash ...`
- `onchainos market portfolio-supported-chains`
- `onchainos market portfolio-dex-history ...`
- `onchainos market portfolio-recent-pnl ...`

Wallet and balance flows should not rely on app-defined business wrappers as the main model-facing interface.
The LLM should reason from the loaded skill plus the generic read-only command tool.

## 3.5 Deterministic Execution Tools

### `execute_swap_buy`
Wraps:

- `onchainos swap execute`

Inputs:

- `from_token`
- `to_token`
- `readable_amount`
- `chain`
- `wallet_address`
- `slippage_policy`
- `gas_policy`

Returns:

- tx hashes
- output amount
- gas used

### `execute_swap_sell`
Wraps:

- `onchainos swap execute`

Inputs:

- held token
- exit token
- amount
- chain
- wallet address

Returns:

- tx hashes
- realized proceeds

## 4. Tool Implementation Guidance

## 4.1 Use typed schemas

Every tool should have:

- a strict input schema,
- a strict output schema,
- normalized field names,
- explicit error shape.

Tool outputs should also include `asset_lane` when lane-specific behavior affects interpretation.

## 4.2 Normalize OKX responses

Do not leak raw CLI fields upward if they are inconsistent.

Normalize inside the command runner / parsing layer used by:

- model-facing generic `onchainos` command tools,
- deterministic execution nodes,
- persistence mappers when raw payloads are stored.

Example:

- `priceImpactPercent` -> `price_impact_pct`
- `swapTxHash` -> `swap_tx_hash`

## 4.3 Separate runtime layers clearly

Suggested structure:

```text
app/services/onchainos_runner.py
app/services/okx_skills.py
app/tools/*.py
app/policies/*.py
app/ta/*.py
```

Where:

- runner / skill services talk to OKX skills / CLI,
- tools expose LangChain-compatible interfaces,
- policies enforce deterministic rules,
- TA computes indicator outputs.

## 4.4 Prefer skills plus a generic command tool over business wrappers

For OKX-covered capabilities, the preferred model-facing pattern is:

- load the relevant skill,
- optionally load referenced docs,
- call a generic read-only `onchainos` tool with the exact command.

Good model-facing tools:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`
- `compute_ta_score`
- `build_trade_sizing_inputs`

Bad model-facing tools:

- `get_wallet_context`
- `get_token_market_snapshot`
- `get_token_risk`
- `get_major_asset_execution_context`

Those business wrappers may still exist for deterministic nodes, but they should not be the primary LLM integration surface.

## 5. Suggested LangChain Registration

Register all possible tools once, then filter them dynamically by agent role and graph stage using middleware.

This matches the LangChain docs pattern for dynamic tool filtering.

## 6. Critical Restriction

For this product:

- parsing agent never gets execution tools,
- decision agent never gets execution tools,
- exit agent never gets execution tools,
- only deterministic graph nodes call execution adapters.

That is the main safety boundary.
