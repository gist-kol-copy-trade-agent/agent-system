# OKX Skill Mapping

## Purpose

This document maps each bot action in the product to the correct `okx-onchainos-skills` skill, including:

- which skill to use,
- the exact command pattern,
- required inputs,
- expected outputs that feed the next step,
- guardrails on when not to use a skill.

This file is written for implementation of the orchestration layer in the v1 product.

## Product Constraints

- V1 is `authorized-auto` only.
- V1 has two execution lanes:
  - `major assets`: `BTC/ETH/SOL`, executed on `X Layer` when funded on `X Layer`
  - `regular tokens`: executed on the resolved signal chain
- No cross-chain bridge or cross-chain swap flow is supported.
- Telegram scraping, message parsing, and TA logic are application-layer responsibilities, not OKX skill responsibilities.

## Global Rules

### Rule 1: Classify the asset lane before trading
Every actionable signal must first be classified into one of:

- `major asset lane`: `BTC`, `ETH`, `SOL`
- `regular token lane`: everything else

### Rule 2: Resolve token identity when the lane requires it
Never trade a regular token by symbol alone. Resolve to:

- `chain`
- `token contract address`
- token type: native vs contract token

Preferred resolution flow:

```bash
onchainos token search --query <symbol_or_ca> --chains <chain>
```

Then confirm or persist:

- `tokenContractAddress`
- `chain`
- `decimal`
- `communityRecognized`

For major assets:

- map the signal to the product-approved X Layer trading representation,
- do not require the full regular-token resolution pipeline,
- do not attempt to mirror the KOL's original venue.

### Rule 3: Use `swap execute` for DEX trades
For buy/sell actions, the primary execution primitive is:

```bash
onchainos swap execute --from <token> --to <token> --readable-amount <amt> --chain <chain> --wallet <wallet_addr>
```

Do not use `wallet contract-call` to submit DEX swaps.

### Rule 4: Security gates depend on the asset lane
Use:

- `security token-scan` for token risk,
- `security tx-scan` only for raw calldata or non-swap contract interactions.

For regular-token swap execution, the minimum required pre-trade security gate is token risk scanning.

For major assets, the product may skip token-specific risk scanning and rely on:

- lane classification,
- quote and execution readiness,
- TA gate,
- wallet and policy checks.

### Rule 5: Chain execution depends on the asset lane

For regular tokens:

- if a Telegram call resolves to a token on `base`, execute on `base`.

For major assets:

- execute on `X Layer`,
- only if the wallet is already funded on `X Layer`.

Do not bridge, rebalance, or move capital across chains inside the bot flow.

## Bot Action Mapping

## 1. Wallet Login and Session Setup

### Action
User starts the bot and authenticates the Agentic Wallet.

### Skills

- Primary: `okx-agentic-wallet`

### Commands

Check session:

```bash
onchainos wallet status
```

Email login:

```bash
onchainos wallet login <email> --locale en-US
onchainos wallet verify <otp>
```

API key login:

```bash
onchainos wallet login
```

Post-login readiness:

```bash
onchainos wallet balance
onchainos wallet addresses
```

### Required Inputs

- email and OTP, or API-key-backed environment

### Outputs Used by Bot

- `loggedIn`
- `currentAccountId`
- `currentAccountName`
- `policy`
- wallet addresses by chain family
- account balances

### Notes

- `wallet status` must run before any wallet-dependent action.
- After successful login, store the active account context locally.

## 2. Wallet Readiness Check Before Trade

### Action
Bot verifies it can trade on the target chain before processing a signal.

### Skills

- Primary: `okx-agentic-wallet`

### Commands

```bash
onchainos wallet status
onchainos wallet balance --chain <chain>
onchainos wallet addresses --chain <chain>
```

### Required Inputs

- target execution `chain`

### Outputs Used by Bot

- available balance on target chain
- correct wallet address for that chain family
- daily/per-tx wallet policy limits

### Notes

- For major assets, the target chain is `X Layer`.
- For regular tokens, the target chain is the resolved signal chain.
- If there is no wallet balance on the target execution chain, the trade must be skipped in V1.
- Do not attempt cross-chain funding.

## 3. Asset Lane Classification

### Action
Bot classifies the signal into a major-asset or regular-token path.

### Skills

- No OKX skill required for the classification itself.

### Logic

- `BTC`, `ETH`, `SOL` -> `major asset lane`
- everything else -> `regular token lane`

### Outputs Used by Bot

- `asset_lane`
- `normalized_asset_symbol`
- `target_execution_chain`

### Notes

- The major-asset lane is a product rule, not an on-chain discovery result.
- `target_execution_chain = xlayer` for the major-asset lane.

## 4. Token Resolution From Telegram Signal

### Action
Bot turns parsed message content into a precise tradable asset.

### Skills

- Primary: `okx-dex-token`

### Commands

Search by symbol/name:

```bash
onchainos token search --query <symbol_or_name> --chains <chain>
```

Fetch token metadata:

```bash
onchainos token info --address <token_ca>
```

Fetch token market metadata:

```bash
onchainos token price-info --address <token_ca>
```

### Required Inputs

- parsed symbol, token name, contract address, and optional chain hint

### Outputs Used by Bot

- `tokenContractAddress`
- `symbol`
- `name`
- `decimal`
- `price`
- `marketCap`
- `liquidity`
- `volume24h`
- `communityRecognized`

### Notes

- This step is mandatory for regular tokens.
- For major assets, use product-approved X Layer trading representations instead of the full regular-token resolution path.
- If multiple matches are returned, the signal is ambiguous and should be skipped unless the parser already extracted a contract address.
- For native-token pairs, use the swap skill's native token address conventions later in execution.

## 5. Token Risk Check

### Action
Bot checks whether the resolved token is obviously unsafe to buy.

### Skills

- Primary: `okx-security`

### Commands

```bash
onchainos security token-scan --tokens "<chainId>:<token_ca>"
```

### Required Inputs

- resolved `chainId`
- resolved `token_ca`

### Outputs Used by Bot

- `isChainSupported`
- `isRiskToken`
- `buyTaxes`
- `sellTaxes`

### Decision Rule

- `isRiskToken = true` -> block buy
- unsupported scan chain -> do not auto-block, but mark reduced-confidence

### Notes

- This is the mandatory token-level safety gate for regular tokens before swap execution.
- The major-asset lane does not require this token-specific step.
- Native tokens are not scanned here.

## 6. Market Enrichment

### Action
Bot fetches market context for scoring and TA.

### Skills

- Primary: `okx-dex-market`
- Supporting: `okx-dex-token`

### Commands

Current price:

```bash
onchainos market price --address <token_ca> --chain <chain>
```

K-line / OHLC:

```bash
onchainos market kline --address <token_ca> --chain <chain>
```

Liquidity / cap / volume:

```bash
onchainos token price-info --address <token_ca>
```

Optional holder concentration:

```bash
onchainos token holders --address <token_ca>
onchainos token advanced-info --address <token_ca>
```

### Required Inputs

- resolved `token_ca`
- resolved `chain`

### Outputs Used by Bot

- current price
- recent candles for TA calculations
- liquidity
- volume
- market cap
- holder concentration
- dev/risk metadata

### Notes

- TA itself is computed in the app, not in the OKX skill.
- For major assets, use a reduced enrichment set centered on price, K-line, quote, and X Layer readiness.
- For regular tokens, keep the richer enrichment path.
- Keep the initial v1 scope focused on a narrow set of metrics: price deviation, recent momentum, liquidity, and volume.

## 7. Smart Money / KOL Overlay

### Action
Bot checks whether the token or chain has corroborating on-chain signal activity.

### Skills

- Primary: `okx-dex-signal`

### Commands

Check supported chains:

```bash
onchainos signal chains
```

Fetch aggregated buy signals:

```bash
onchainos signal list --chain <chain> --token-address <token_ca>
```

Optional raw activity feed:

```bash
onchainos tracker activities --tracker-type smart_money --chain <chain>
onchainos tracker activities --tracker-type kol --chain <chain>
```

### Required Inputs

- resolved `chain`
- optional `token_ca`

### Outputs Used by Bot

- presence or absence of recent buy-side signal support
- wallet type mix: smart money / KOL / whale
- trigger wallet count

### Notes

- This is an enrichment feature, not a hard execution dependency.
- It is optional for regular tokens and not required for the major-asset lane.
- If the chain is unsupported for signals, continue without this signal.

## 8. Quote and Route Check Before Buy

### Action
Bot asks the DEX aggregator for a read-only quote before taking the trade.

### Skills

- Primary: `okx-dex-swap`

### Commands

Quote:

```bash
onchainos swap quote --from <from_token> --to <to_token> --readable-amount <amt> --chain <chain>
```

Optional liquidity-source inspection:

```bash
onchainos swap liquidity --chain <chain>
```

### Required Inputs

- `from_token`: usually stablecoin or native token address on the target execution chain
- `to_token`: target token contract address or approved major-asset representation
- `readable_amount`
- `chain`

### Outputs Used by Bot

- `toTokenAmount`
- `fromTokenAmount`
- `estimateGasFee`
- `tradeFee`
- `priceImpactPercent`
- `dexRouterList`
- `fromToken.isHoneyPot`
- `toToken.isHoneyPot`
- token tax rates

### Decision Rule

- no quote -> skip trade
- honeypot on target buy path -> block trade
- price impact above configured hard cap -> block trade
- otherwise continue to decision engine

## 9. Buy Execution

### Action
Bot executes the approved buy on the same chain.

### Skills

- Primary: `okx-dex-swap`

### Commands

```bash
onchainos swap execute \
  --from <from_token> \
  --to <to_token> \
  --readable-amount <amt> \
  --chain <chain> \
  --wallet <wallet_addr> \
  [--slippage <pct>] \
  [--gas-level <slow|average|fast>] \
  [--mev-protection]
```

### Required Inputs

- wallet address for resolved chain
- source asset address
- destination token address
- trade amount in human-readable units
- chain
- optional slippage and gas settings

### Outputs Used by Bot

- `approveTxHash` if approval occurred
- `swapTxHash`
- `fromAmount`
- `toAmount`
- `priceImpact`
- `gasUsed`

### Notes

- This command is the correct trading primitive for buys and sells.
- The bot should log quote context and execution result together.
- For major assets, `chain = xlayer`.
- For regular tokens, `chain = resolved signal chain`.
- For Solana MEV, use `--tips`; for supported EVM chains, use `--mev-protection` when policy says so.

## 10. Exit Execution

### Action
Bot exits an existing position when exit conditions trigger.

### Skills

- Primary: `okx-dex-swap`

### Commands

Quote exit:

```bash
onchainos swap quote --from <held_token> --to <exit_token> --readable-amount <amt> --chain <chain>
```

Execute exit:

```bash
onchainos swap execute --from <held_token> --to <exit_token> --readable-amount <amt> --chain <chain> --wallet <wallet_addr>
```

### Required Inputs

- held token contract
- exit token contract, usually USDC/USDT/native on the same chain
- sell amount
- chain
- wallet address

### Outputs Used by Bot

- exit tx hash
- realized exit amount
- gas used

### Notes

- Exit is just another same-chain swap.
- There is no native TP/SL order primitive in this product.

## 11. Portfolio Snapshot

### Action
Bot reports current wallet holdings and value.

### Skills

- If using the logged-in wallet: `okx-agentic-wallet`
- If using a provided address: `okx-wallet-portfolio`

### Commands

Logged-in wallet:

```bash
onchainos wallet balance
onchainos wallet balance --chain <chain>
```

Explicit address:

```bash
onchainos portfolio total-value --address <addr> --chains "<chain_list>"
onchainos portfolio all-balances --address <addr> --chains "<chain_list>"
```

### Required Inputs

- either current logged-in wallet context, or explicit wallet address

### Outputs Used by Bot

- total portfolio value
- token balances
- chain distribution

### Notes

- For the bot's own operating portfolio, prefer `wallet balance`.

## 12. Position and PnL Review

### Action
Bot summarizes wallet trading results and recent DEX behavior.

### Skills

- Primary: `okx-dex-market`

### Commands

Portfolio overview:

```bash
onchainos market portfolio-supported-chains
onchainos market portfolio-overview --address <addr> --chain <chain>
```

DEX history:

```bash
onchainos market portfolio-dex-history --address <addr> --chain <chain> --begin <ms> --end <ms>
```

Recent PnL:

```bash
onchainos market portfolio-recent-pnl --address <addr> --chain <chain>
onchainos market portfolio-token-pnl --address <addr> --chain <chain> --token-address <token_ca>
```

### Required Inputs

- wallet address
- supported chain
- optional time window

### Outputs Used by Bot

- win rate
- realized/unrealized PnL
- recent token-level performance
- DEX transaction history

### Notes

- The bot should still maintain its own internal trade ledger; these endpoints are supporting analytics, not the single source of truth for bot decisions.

## 13. Raw Contract Interaction

### Action
Bot performs a non-swap contract interaction.

### Skills

- Primary: `okx-agentic-wallet`
- Mandatory risk gate: `okx-security`

### Commands

Security scan:

```bash
onchainos security tx-scan --chain <chain> --from <wallet_addr> --to <target_addr> --data <calldata> [--value <wei_or_hex>]
```

If safe, execute:

```bash
onchainos wallet contract-call --to <target_addr> --chain <chain> --input-data <calldata> [--amt <minimal_native_units>]
```

### Required Inputs

- wallet address
- target address
- chain
- calldata
- optional attached native value

### Outputs Used by Bot

- tx-scan `action`
- simulation result
- tx hash / execution result

### Notes

- This is for non-swap flows only.
- Do not use this path for regular buy/sell execution.

## 14. Raw Transaction Broadcast and Tracking

### Action
Bot broadcasts or tracks a signed transaction produced elsewhere.

### Skills

- Primary: `okx-onchain-gateway`

### Commands

Gas:

```bash
onchainos gateway gas --chain <chain>
```

Simulation:

```bash
onchainos gateway simulate --from <from> --to <to> --data <data> --chain <chain>
```

Broadcast:

```bash
onchainos gateway broadcast --signed-tx <signed_tx> --address <wallet_addr> --chain <chain>
```

Track:

```bash
onchainos gateway orders --address <wallet_addr> --chain <chain> [--order-id <order_id>]
```

### Required Inputs

- signed tx payload
- sender address
- chain

### Outputs Used by Bot

- gas quote
- simulation status
- `orderId`
- order / tx status

### Notes

- This is not the normal path for v1 buy/sell trading.
- Use mainly for advanced integrations or externally signed flows.

## 15. Audit Log Access

### Action
Developer needs local OnchainOS audit location for troubleshooting.

### Skills

- Primary: `okx-audit-log`

### Output

- log path: `~/.onchainos/audit.jsonl`

### Notes

- Do not expose log contents to end users by default.

## Product Flow to Skill Flow

## A. New Telegram Signal -> Buy Decision -> Buy Execution

### Steps

1. App layer parses Telegram message.
2. Classify asset lane.
3. If regular token, resolve token:

```bash
onchainos token search --query <symbol_or_ca> --chains <chain>
onchainos token price-info --address <token_ca>
```

4. Check wallet readiness:

```bash
onchainos wallet status
onchainos wallet balance --chain <chain>
onchainos wallet addresses --chain <chain>
```

For major assets, `chain = xlayer`.

5. If regular token, apply token risk gate:

```bash
onchainos security token-scan --tokens "<chainId>:<token_ca>"
```

6. Market enrichment:

```bash
onchainos market price --address <token_ca> --chain <chain>
onchainos market kline --address <token_ca> --chain <chain>
```

For major assets, use the approved X Layer asset representation.

7. Optional signal overlay for regular tokens:

```bash
onchainos signal list --chain <chain> --token-address <token_ca>
```

8. Quote:

```bash
onchainos swap quote --from <funding_token> --to <token_ca> --readable-amount <amt> --chain <chain>
```

9. Execute:

```bash
onchainos swap execute --from <funding_token> --to <token_ca> --readable-amount <amt> --chain <chain> --wallet <wallet_addr>
```

## B. Position Exit

### Steps

1. App layer detects exit trigger.
2. Refresh quote:

```bash
onchainos swap quote --from <held_token> --to <exit_token> --readable-amount <amt> --chain <chain>
```

3. Execute sell:

```bash
onchainos swap execute --from <held_token> --to <exit_token> --readable-amount <amt> --chain <chain> --wallet <wallet_addr>
```

## C. Telegram `/portfolio`

### Steps

1. Logged-in wallet summary:

```bash
onchainos wallet balance
```

2. Optional analytics:

```bash
onchainos market portfolio-overview --address <wallet_addr> --chain <chain>
```

## D. Telegram `/history`

### Steps

1. Bot-local database is primary.
2. Optional chain analytics support:

```bash
onchainos market portfolio-dex-history --address <wallet_addr> --chain <chain> --begin <ms> --end <ms>
```

## Actions Outside OKX Skills

These actions must be implemented in the application layer:

- Telegram scraping / webhook ingestion
- LLM parsing and intent extraction
- KOL credibility scoring
- trade sizing logic
- TA indicator computation
- active position registry
- exit trigger engine
- Telegram message formatting and bot UX
- local persistence and bot audit trail

## Recommended Minimal Integration Set for V1

If v1 should stay narrow, the minimum useful skill set is:

- `okx-agentic-wallet`
- `okx-dex-market`
- `okx-dex-swap`

Required for the regular-token lane:

- `okx-dex-token`
- `okx-security`

Optional for better signal quality or analytics:

- `okx-dex-signal`
- `okx-wallet-portfolio`
- `okx-onchain-gateway`
- `okx-audit-log`
