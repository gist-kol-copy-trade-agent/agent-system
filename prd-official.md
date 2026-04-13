# PRD: Agentic On-Chain Copy Trading Assistant

## 1. Product Summary

### 1.1 Objective
Build a single-user AI trading assistant that monitors Telegram KOL channels, detects actionable trade calls, enriches them with on-chain and market data via OKX OnchainOS skills, and executes approved spot token trades through the user's OKX Agentic Wallet.

### 1.2 Product Positioning
This product is not a fully autonomous hedge fund and not a generic multi-user SaaS platform. It is a personal trading automation system optimized for:

- fast reaction to KOL trade calls,
- transparent AI-assisted decisioning,
- strict risk controls,
- verifiable on-chain execution.

### 1.3 Core Value Proposition
The system reduces the manual workflow of:

1. reading Telegram calls,
2. identifying the token and chain,
3. checking whether the token is tradable and safe enough,
4. checking liquidity and market context,
5. sizing the trade,
6. executing the trade,
7. monitoring the position and exiting when rules trigger.

## 2. Product Goals

### 2.1 Primary Goals

- Ingest Telegram KOL messages and classify whether a message is a tradeable call.
- Resolve the referenced asset into an exact on-chain token contract and chain.
- Enrich the signal with wallet state, token data, market data, and security checks.
- Apply deterministic risk rules before any execution.
- Execute same-chain spot swaps through OKX OnchainOS when the setup passes all gates.
- Track open positions and trigger exits based on predefined logic.
- Deliver full decision summaries and execution logs to Telegram.

### 2.2 Non-Goals

- Any cross-chain bridge or cross-chain swap workflow.
- Multi-user account management, tenant isolation, or broker-style shared infrastructure.
- Native derivatives trading, leverage, perpetuals, or CEX order-book trading.
- Exchange-native TP/SL order management.
- Fully trustless historical backtesting with tick-level fill accuracy.
- A sophisticated quant TA engine with dozens of built-in indicators from OKX skills.

## 3. Product Principles

- Safety first: no trade should be executed if token identity, wallet state, or risk verdict is unclear.
- Explainability: every decision sent to the user must include a compact reason summary.
- Capability realism: product logic must reflect actual OnchainOS capabilities, not assumed platform behavior.
- Modularity: parsing, enrichment, decisioning, execution, and monitoring should be isolated modules.
- Single-user focus: optimize for reliability and iteration speed over premature platform complexity.

## 4. Supported Capability Model

This section defines what is considered in-scope based on the current `okx-onchainos-skills` repository.

### 4.1 Agentic Wallet
Supported through `okx-agentic-wallet`:

- login and session status,
- wallet addresses by chain family,
- authenticated balance queries,
- token transfers,
- transaction history,
- smart contract calls,
- message signing.

Implication for the product:
The assistant can manage the user's authenticated wallet lifecycle and can execute wallet-driven actions once the user is logged in.

### 4.2 On-Chain and Market Data
Supported across `okx-dex-market`, `okx-dex-token`, `okx-wallet-portfolio`, and `okx-dex-signal`:

- token search and metadata,
- token price, market cap, liquidity, and 24h volume,
- OHLC/K-line data,
- wallet balances and holdings,
- wallet PnL and DEX history,
- smart money / KOL / whale activity from supported on-chain signal feeds,
- token holder distribution and advanced token metadata.

Implication for the product:
The assistant can enrich Telegram-derived trade ideas with real market and token data, but Telegram scraping itself is an external subsystem and not provided by OnchainOS.

### 4.3 Transaction Execution
Supported through `okx-dex-swap`, `okx-agentic-wallet`, `okx-onchain-gateway`, and `okx-security`:

- same-chain DEX quote and swap execution,
- approval flows handled by the swap execution path,
- wallet-based contract calls for non-swap interactions,
- gas estimation, simulation, broadcast, and order tracking for raw transactions,
- token and transaction security scanning.

Implication for the product:
The default execution primitive for buys and sells should be `swap execute` on a specific chain. Raw contract calls should only be used for non-swap interactions. Security scans must be part of the execution pipeline.

### 4.4 Explicit Capability Limits

- Cross-chain bridge and cross-chain swap workflows are out of scope for this product.
- TA indicators are not a built-in OnchainOS skill abstraction; they must be computed by the application from fetched OHLCV/K-line data.
- DEX execution is swap-based. Position exits are implemented by submitting a sell swap when exit conditions trigger, not by placing native stop-loss or take-profit exchange orders.
- Historical K-line and price data support heuristic replay and evaluation, but not exchange-grade historical backtests with exact entry fill simulation.

## 5. Target User

### 5.1 Primary User
A single advanced crypto trader who:

- follows Telegram KOL channels actively,
- wants faster reaction time,
- is comfortable with wallet-based on-chain trading,
- wants AI assistance but still requires visibility and control.

### 5.2 User Pain Points

- too many Telegram calls to monitor manually,
- low confidence in token quality and timing,
- slow manual verification of contract address and chain,
- poor execution speed,
- inconsistent risk sizing,
- no structured log of why a trade was or was not taken.

## 6. End-to-End User Flow

1. The user sets up the bot and authenticates an OKX Agentic Wallet.
2. The user submits one or more Telegram channels to follow.
3. The ingestion service receives new channel messages from an external scraper/webhook.
4. The AI parser classifies the message and extracts trading intent.
5. The orchestration layer resolves token identity and chain.
6. The enrichment layer gathers wallet state, token data, market data, and security/risk context.
7. The decision engine applies deterministic gating and position sizing rules.
8. If execution is allowed under the current mode, the system submits a same-chain swap.
9. The monitoring service tracks the position and relevant follow-up messages.
10. The bot reports reasoning, execution status, and ongoing position state to Telegram.

## 7. Functional Requirements

### 7.1 Onboarding and Wallet Setup

The system must:

- allow the user to authenticate an OKX Agentic Wallet,
- verify wallet login state before any wallet-dependent action,
- fetch wallet addresses and balances after successful login,
- show a readiness summary in Telegram,
- persist the active wallet/account context locally.

The system must not:

- assume wallet login or active account state without verification,
- execute trades before wallet balance and chain compatibility are confirmed.

#### Trading Style and Global Settings

During onboarding, the system should initialize a user-level strategy profile.

The default UX should be:

1. user chooses one base style:
   - `degen`
   - `normal`
   - `safe`
2. the agent proposes a recommended default parameter set,
3. the user can accept the defaults or override any parameter by chatting with the bot,
4. the system stores the final settings as persistent global strategy state for that user.

The base style is a preset, not the full configuration.

The agent should propose at least the following parameters:

- `max_amount_per_trade_usd`
- `max_portfolio_risk_pct_per_trade`
- `max_active_positions`
- `major_asset_max_amount_usd`
- `regular_token_max_amount_usd`
- `max_slippage_pct_major`
- `max_slippage_pct_regular`
- `max_price_deviation_pct_major`
- `max_price_deviation_pct_regular`
- `min_liquidity_usd_regular`
- `default_stop_loss_pct`
- `default_take_profit_pct`
- `max_holding_time_hours`
- `major_asset_lane_enabled`
- `regular_token_lane_enabled`

Recommended PoC behavior:

- `safe` -> smaller size, tighter slippage, stricter liquidity and deviation gates
- `normal` -> balanced defaults
- `degen` -> larger size, looser slippage, looser liquidity thresholds, but still bounded by hard system caps

The system must allow the user to override any of these settings through natural-language chat, for example:

- "set max amount per trade to 300 USDT"
- "disable regular-token trades"
- "set major trades to max 1,000 USDT"
- "make stop loss tighter"

The system must persist the final strategy profile and use it as global decision context for every future signal.

### 7.2 Telegram Channel Registration

The system must:

- allow the user to register a Telegram channel or source,
- persist source metadata and status,
- support pause/stop per source,
- track whether a source has enough parsed history to compute credibility heuristics.

### 7.3 Message Ingestion and Intent Extraction

The system must:

- receive new Telegram messages from an external scraper or webhook,
- classify messages into at least:
  - actionable trade call,
  - trade update / exit signal,
  - noise / shilling / non-trade content,
- extract when present:
  - token symbol,
  - contract address,
  - chain hints,
  - entry price or entry zone,
  - target and stop guidance,
  - urgency markers.

The system should:

- fall back to "needs review" when token identity is ambiguous,
- prefer contract address over symbol/name when both exist.

### 7.4 Token Resolution and Asset Routing

The system must:

- resolve every trade candidate into an exact token contract and chain before scoring,
- use token search and metadata lookups to disambiguate symbols,
- block execution if token identity remains ambiguous.

The product distinguishes between two asset lanes:

#### Lane A: Major Assets

This lane is limited to:

- BTC
- ETH
- SOL

PoC/V1 note:

- this major-asset list is intentionally fixed to these three assets for the initial version
- future versions may expand the list to additional large-cap assets such as `BNB` and `TRX`
- the product should treat the major-asset set as a configurable allowlist rather than a permanent hardcoded business assumption

For major assets:

- the system may trade a standardized major-asset representation on X Layer,
- the system does not need token-level metadata enrichment, holder analysis, or token risk scanning beyond the normal execution and quote checks,
- the system should prioritize TA-driven entry filtering and execution readiness,
- the system may ignore whether the KOL originally bought on a CEX or another DEX venue.

Major-asset execution rule:

- the execution venue for this lane is X Layer,
- this is a product-level strategy choice, not a cross-chain routing flow,
- the system must only execute if the required trading capital is already available on X Layer,
- the system must not bridge funds automatically to X Layer.

#### Lane B: Regular Tokens

For all other assets:

- the system must follow the regular token-resolution and enrichment pipeline,
- the system must execute on the chain of the resolved token signal,
- the system may compare same-chain routes and liquidity sources only,
- the system must not move capital across chains as part of the trading flow.

If a regular token is called on a specific chain:

- the system should trade on that resolved chain,
- subject to a stricter allowlist of supported chains and tokens if configured.

### 7.5 KOL Profiling and Cold Start Evaluation

The system should support a lightweight source evaluation workflow:

1. ingest a sample of recent messages,
2. identify which messages appear to be trade calls,
3. resolve the referenced tokens where possible,
4. compare message-time reference price versus later observed market price,
5. compute heuristic source metrics such as hit rate and average return.

This module must be described as heuristic source scoring, not as a precise backtest engine.

The system must disclose that:

- some messages will be unparseable,
- some calls will not contain exact entry timing,
- reconstructed returns are approximate,
- execution assumptions may differ from real fills.

### 7.6 On-Chain and Market Enrichment

The enrichment policy depends on the asset lane.

#### Major Assets (`BTC/ETH/SOL`)

For major assets, the system should use a simplified enrichment path focused on:

- current wallet balance on X Layer,
- current price and recent K-line/OHLCV data,
- quote availability and price impact on X Layer,
- execution readiness on X Layer.

For this lane, the system does not need to run the full token-level research pipeline such as:

- token metadata validation,
- holder concentration analysis,
- advanced token risk analysis for alt tokens,
- smart-money token-specific overlays as a hard dependency.

#### Regular Tokens

For each actionable regular-token candidate, the system must fetch as many applicable signals as possible:

- current wallet balance on the relevant chain,
- token price and market metadata,
- liquidity and volume,
- recent K-line/OHLCV data,
- token holder concentration and advanced token metadata when needed,
- smart-money/KOL/whale activity when supported by chain and token,
- security scan outputs for token and transaction safety.

For regular tokens, risk assessment should combine at least two layers:

- security-layer risk from `okx-security` token scanning
- token-intelligence risk from `okx-dex-token` advanced metadata

Examples of token-intelligence fields that should be captured when available:

- `riskControlLevel`
- `tokenTags`
- `devRugPullTokenCount`
- `devCreateTokenCount`
- `top10HoldPercent`
- `lpBurnedPercent`
- `creatorAddress`

The system should explicitly separate:

- Telegram-derived social signal,
- on-chain wallet activity signal,
- market structure signal,
- security risk signal.

### 7.7 Technical Analysis Layer

For V1, TA is an application-side rule layer computed from fetched K-line/OHLCV data.

The system may include simple indicators and filters such as:

- entry deviation from call price,
- momentum over recent candles,
- relative drawdown from local highs,
- breakout or pullback heuristics,
- candle-based volatility filters.

The system must not claim that OnchainOS natively provides a full TA engine.

The system should start with a narrow, deterministic TA policy:

- anti-FOMO deviation threshold,
- recent liquidity and volume threshold,
- optional momentum confirmation,
- optional volatility cap.

TA role by lane:

- for major assets, TA is the primary analysis layer before execution,
- for regular tokens, TA is one input inside a broader token-risk and liquidity-aware pipeline.

### 7.8 Trade Decision Engine

The decision engine must combine:

- source confidence,
- token and on-chain risk score,
- market/TA score,
- wallet balance and exposure state,
- user global strategy settings,
- configured max risk per trade.

Suggested sizing model:

`trade_amount = available_stable_balance x max_risk_pct x source_score x token_score x ta_score`

The implementation must also enforce hard risk caps:

- maximum notional per trade,
- maximum number of active positions,
- maximum portfolio exposure per chain,
- maximum exposure to unverified or low-liquidity tokens.

Lane-specific interpretation:

- major assets may use a simplified score stack centered on source confidence, TA score, and X Layer execution readiness,
- regular tokens must use the full score stack including token and on-chain risk inputs.

Global strategy settings must act as decision modifiers, not just UI preferences. At minimum, they must affect:

- whether a lane is enabled,
- maximum trade amount,
- maximum risk per trade,
- slippage tolerance,
- anti-FOMO deviation thresholds,
- regular-token minimum liquidity threshold,
- default stop-loss / take-profit assumptions when the signal lacks explicit exits,
- active position limits.

### 7.9 Execution Engine

For V1, trade execution must use same-chain spot swaps as the primary mechanism.

The execution policy depends on the asset lane.

#### Major Assets (`BTC/ETH/SOL`)

The system must:

- map the signal into the supported major-asset trading representation on X Layer,
- check that the wallet has sufficient executable balance on X Layer,
- fetch a quote on X Layer,
- apply TA-based entry gating,
- submit the trade through OKX swap execution on X Layer,
- record that the trade followed the major-asset lane.

The system must not:

- attempt to mirror the KOL's original venue,
- attempt to infer or reproduce the KOL's original execution path,
- bridge funds to X Layer automatically.

#### Regular Tokens

The system must:

- fetch a quote before execution,
- verify token contract identity again before execution,
- run required security checks,
- warn or block on high price impact, honeypot risk, or unsafe transaction verdicts,
- submit the trade through OKX swap execution on the selected chain,
- record transaction hashes, quote context, and decision inputs.

The system must not:

- use wallet contract-call to submit DEX swaps when `swap execute` is the correct primitive,
- describe raw on-chain broadcast as proof of completed economic settlement,
- perform or imply any cross-chain routing, bridge, or capital transfer as part of trade execution.

### 7.10 Post-Trade Monitoring and Exit Logic

The system must maintain an active-position registry containing:

- source channel,
- token and chain,
- entry timestamp,
- entry cost basis estimate,
- transaction hashes,
- current status,
- latest price snapshot,
- exit policy state.

Exit triggers may include:

- KOL follow-up exit message,
- static take-profit threshold,
- static stop-loss threshold,
- trailing-stop logic based on current price,
- risk-off trigger from security or liquidity deterioration,
- maximum holding time.

When an exit condition triggers, the system should execute a sell swap on the same chain where the position is held.

### 7.11 Telegram Interface

Minimum command set:

- `/start` for onboarding,
- `/trade-style` to view or update the global trading style and strategy parameters,
- `/follow <channel>` to add a source,
- `/stop <channel>` to stop following,
- `/portfolio` to show active positions and wallet summary,
- `/history` to show completed trades and channel performance,
- `/status` to show system mode, wallet state, and source count.

Every important automation step must send a compact explanation back to Telegram.

The `/trade-style` command should support both:

- preset selection (`degen`, `normal`, `safe`)
- parameter-level customization and review

## 8. Risk and Safety Requirements

### 8.1 Execution Safety

The system must block execution when:

- token identity is ambiguous,
- wallet balance is insufficient,
- token scan or transaction scan returns a block verdict,
- quote is unavailable,
- price impact exceeds configured hard limits,
- required chain or liquidity checks fail.

### 8.2 Approval and Security Policy

The system must:

- run token and transaction risk checks where applicable,
- respect warn/block results from security tooling,
- log when a scan could not be completed,
- require explicit user policy on whether automation may proceed when a scan fails for infrastructure reasons.

### 8.3 Transparency

For every skipped or executed trade, Telegram should receive a short decision summary, for example:

- detected token and chain,
- reason score summary,
- risk findings,
- trade size,
- whether the action was blocked, skipped, or executed.

### 8.4 Operating Modes

For the PoC and V1 scope, the system supports a single operating mode:

- `authorized-auto`: execution allowed automatically within predefined policy bounds.

`confirm-first` is out of scope for the initial version and may be added later if needed.

Even in `authorized-auto`, the system must still halt on hard risk blocks.

## 9. Data and State Requirements

The product should persist the following core entities:

- usersettings,
- user_strategy_profile,
- wallet_session_state,
- followed_sources,
- source_message_log,
- parsed_signal_candidates,
- token_resolution_records,
- enrichment_snapshots,
- trade_decisions,
- execution_records,
- active_positions,
- closed_positions,
- audit_events.

Minimum persistence expectations:

- selected trading style,
- resolved global strategy parameters,
- source and channel state,
- parsed message outputs,
- all execution attempts,
- quote context at trade time,
- exit reasons,
- user-visible decision summaries.

## 10. System Architecture

### 10.1 Logical Components

- Telegram Bot Interface
- Telegram Scraper / Webhook Ingestion Service
- LLM Parsing and Reasoning Layer
- Signal Resolution and Enrichment Service
- Rule-Based Decision Engine
- OKX OnchainOS Execution Adapter
- Position Monitor and Exit Manager
- Local Persistence Layer

### 10.2 Recommended Stack

- Language: Python
- Bot and orchestration: Python async services
- LLM integration: function-calling capable model layer
- Database: PostgreSQL for persistent state
- Queue/eventing: lightweight async job queue or event bus
- Deployment: Dockerized single-user service

SQLite is acceptable for prototyping, but PostgreSQL is preferred for the official build path.

## 11. MVP Scope

The MVP should include:

- one authenticated user,
- Telegram source registration,
- webhook-based message ingestion,
- trade-call classification,
- asset-lane classification between:
  - major assets (`BTC/ETH/SOL`)
  - regular tokens,
- token resolution,
- wallet balance lookup,
- market and token enrichment,
- basic risk scoring,
- major-asset execution on X Layer when funded on X Layer,
- regular-token execution on the resolved signal chain,
- active-position monitoring,
- sell-on-exit execution,
- Telegram summaries and audit logs,
- a demo flow that shows:
  - one major-asset case,
  - one regular-token case.

The MVP should exclude:

- any bridge-based or cross-chain capital routing,
- advanced multi-factor portfolio optimization,
- multi-user tenancy,
- DeFi vault automation,
- exchange-native conditional orders.

## 12. Success Metrics

### 12.1 Product Metrics

- percentage of incoming messages correctly classified,
- percentage of trade candidates successfully resolved to token + chain,
- execution success rate,
- average time from message receipt to trade submission,
- percentage of blocked trades with valid risk rationale,
- user override rate,
- source-level realized performance summary.

### 12.2 Safety Metrics

- number of blocked unsafe trades,
- number of failed executions,
- number of trades attempted without complete enrichment data,
- number of unresolved token identity cases,
- number of automation events executed outside configured policy.

## 13. Delivery Roadmap

### Phase 1: Core MVP

- wallet onboarding,
- Telegram ingestion,
- message parsing,
- token resolution,
- enrichment,
- basic scoring,
- same-chain swap execution,
- active position tracking,
- Telegram reporting.

### Phase 2: Better Signal Quality

- stronger source scoring,
- richer heuristics for Telegram parsing,
- improved TA filters,
- deeper token concentration and holder analysis,
- on-chain signal overlays from smart money / KOL / whale feeds.

### Phase 3: Advanced Automation

- configurable strategy templates,
- richer portfolio exposure rules,
- richer portfolio-level risk controls within supported single-chain execution flows,
- more robust analytics and reporting.

## 14. Final Product Definition

The official product direction is:

An English-language, single-user, Telegram-driven on-chain copy-trading assistant that uses OKX OnchainOS for wallet operations, market and token enrichment, security checks, and same-chain DEX swap execution, while keeping signal parsing, TA logic, source scoring, and orchestration in the application layer.

Cross-chain bridge or swap behavior is not part of the official product definition. Advanced native TA support from OnchainOS and exchange-style TP/SL are also out of scope.
