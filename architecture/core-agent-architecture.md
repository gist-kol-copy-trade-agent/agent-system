# Core Sub-Agent Architecture

## 1. Design Goals

The core sub-agent system must:

- reason well enough to parse noisy Telegram KOL calls,
- use tools selectively and with bounded context,
- survive retries, crashes, and partial failures through a persistent Postgres-backed checkpointer,
- keep trading actions deterministic after the decision boundary,
- maintain a clean separation between agent state and business persistence.

## 2. LangChain / LangGraph Positioning

Based on the LangChain docs:

- `create_agent` is the right abstraction for the standard model-tools loop.
- LangGraph is the right runtime for checkpoints, thread-scoped state, and recovery.
- middleware is the right place for context engineering, dynamic prompt shaping, and tool filtering.
- runtime context is the right place for dependency injection.
- short-term memory belongs in graph state and checkpointer-backed threads.
- long-term memory belongs in a store, not in the model prompt by default.

For this product, the recommended architecture is:

- LangChain sub-agents for bounded reasoning tasks.
- LangGraph state graph for orchestration and failure recovery.
- OKX OnchainOS skills loaded by the agent as prompt specializations.
- Application services mainly for skill loading, deterministic execution control, TA calculation, Telegram IO, and persistence.

Identity model note:

- these are not independently deployed on-chain agents,
- they are bounded sub-agents inside one orchestrated runtime,
- they share a single Agentic Wallet identity boundary for execution.

Current MVP note:

- runtime orchestration is implemented with LangGraph,
- the default runtime is configured for a Postgres-backed LangGraph checkpointer,
- tests and minimal local validation can still override the backend to `memory`.

The product also has two execution lanes:

- `major asset lane`: `BTC/ETH/SOL`, execute on `X Layer`, simplified analysis
- `regular token lane`: full pipeline on the resolved signal chain

## 3. High-Level Topology

```text
Telegram/Webhook
  -> Signal Intake Graph
      -> Parsing Agent
      -> Deterministic Resolver + Enrichment Nodes
      -> Decision Agent
      -> Deterministic Policy Gate
      -> Execution Node
      -> Persistence + Notification

Position Monitor Scheduler
  -> Exit Evaluation Graph
      -> Market Refresh Nodes
      -> Exit Decision Agent
      -> Deterministic Exit Gate
      -> Execution Node
      -> Persistence + Notification

User Command Router
  -> Command-specific Graphs / Handlers
      -> Portfolio / History / Follow / Stop / Status
```

## 4. Recommended Sub-Agent Partitioning

Do not use one monolithic agent for all responsibilities.

Use bounded sub-agent roles:

### 4.1 Parsing Sub-Agent
Purpose:

- classify Telegram message type,
- extract structured trade intent,
- normalize ambiguous language into a fixed schema.

The parsing sub-agent should not execute trades.

### 4.2 Decision Sub-Agent
Purpose:

- synthesize parsed signal, market data, security data, wallet state, and TA outputs,
- produce a structured trade decision recommendation,
- explain why a trade should be executed, skipped, or blocked.

The decision sub-agent should not directly call raw execution tools.

### 4.3 Exit Sub-Agent
Purpose:

- interpret active position state, market conditions, and user settings,
- recommend whether an active position should be held, hard-exited, or managed via trailing logic,
- output a structured exit decision.

The exit sub-agent should not directly mutate portfolio state.

### 4.4 Wallet, Portfolio, and History Command Sub-Agents
Purpose:

- `WalletAgent` handles `/start` and `/status` with `okx-agentic-wallet`,
- `PositionTrackerAgent` handles `/portfolio` with `okx-dex-market`,
- `HistoryAgent` handles `/history` with `okx-dex-market`.

These sub-agents should not directly execute unrestricted trade side effects.

### 4.5 Swap Execution Sub-Agent
Purpose:

- receive already policy-approved buy or sell intent,
- load `okx-dex-swap` skill,
- synthesize route / execution details,
- invoke bounded swap execution tools.

This sub-agent must not decide whether execution is allowed.
That remains outside the agent in deterministic policy-gate nodes.

## 5. Why Not a Single Always-On General Agent

A single unrestricted agent would create avoidable failure modes:

- too many tools in context,
- higher risk of wrong tool selection,
- harder debugging,
- weaker auditability,
- unsafe trade execution paths.

The LangChain docs emphasize context engineering and dynamic tool availability. This product should use that aggressively.

## 6. Graph-Level Architecture

## 6.1 Primary Graph: Signal Intake and Trade Execution

Recommended node sequence:

1. `ingest_signal`
2. `parse_signal_agent`
3. `validate_parse`
4. `classify_asset_lane`
5. `resolve_target_asset`
6. `load_wallet_context`
7. `fetch_market_context`
8. `compute_ta`
9. `fetch_optional_signal_overlay`
10. `run_conditional_security_checks`
11. `decision_agent`
12. `apply_policy_gate`
13. `swap_execution_agent`
14. `persist_trade_result`
15. `notify_telegram`

## 6.2 Secondary Graph: Position Monitoring and Exit

Recommended node sequence:

1. `load_position`
2. `load_strategy_profile`
3. `refresh_market_context`
4. `refresh_ta`
5. `build_exit_inputs`
6. `exit_decision_agent`
7. `apply_exit_policy_gate`
8. `persist_hold_or_trailing_state`
9. `swap_execution_agent`
10. `persist_exit_result`
11. `notify_telegram`

## 6.3 Command Graphs

Keep command flows simple and mostly deterministic:

- `/start` -> `WalletService` wallet graph with `WalletAgent`
- `/trade-style` -> strategy profile command graph
- `/follow` -> source registration graph
- `/stop` -> source pause graph
- `/portfolio` -> portfolio summary graph with `PositionTrackerAgent`
- `/history` -> `HistoryAgent` + local history graph
- `/status` -> `WalletService` readiness graph with `WalletAgent`

## 7. Where the Model Should Be Called

The model should only be called at ambiguity-heavy steps:

- Telegram message classification and extraction
- decision synthesis
- exit decision synthesis
- wallet login, verification, and status handling through `WalletAgent` + `okx-agentic-wallet`
- portfolio / token PnL tracking through `PositionTrackerAgent` + `okx-dex-market`
- DEX history retrieval through `HistoryAgent` + `okx-dex-market`
- optional user-facing summary generation

The model should not be the primary decision maker for:

- token contract resolution after deterministic search results exist,
- TA math,
- security verdict interpretation,
- price impact thresholds,
- risk cap enforcement,
- execution eligibility.

It also should not decide whether a token is in the major-asset allowlist. That is a deterministic product rule.

Wallet and balance retrieval are a special case:

- the underlying OKX capability is still invoked through model tool calls using `okx-agentic-wallet`,
- but any final trading permission checks that depend on wallet state remain deterministic after the model step.

## 8. Tool Exposure Strategy

## 8.1 Tools Exposed to Parsing Agent

Expose a small skill-first tool surface:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Do not expose:

- execution tools
- wallet mutation tools
- raw contract call tools

## 8.2 Tools Exposed to Decision Agent

Expose:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`
- `compute_ta_score`
- `build_trade_sizing_inputs`

Do not expose:

- `execute_swap_*`
- `wallet_contract_call`
- gateway broadcast tools

The decision agent outputs a typed decision object, not side effects.

The graph or middleware should filter skill availability by lane:

- major asset lane: prefer `okx-agentic-wallet`, `okx-dex-market`, `okx-dex-swap`
- regular token lane: add `okx-dex-token` and `okx-security`

## 8.3 Tools Exposed to Exit Agent

Expose:

- `get_position_snapshot`
- `get_token_market_snapshot`
- `compute_exit_ta_score`

Do not expose direct write tools.

## 8.4 Tools Exposed to WalletAgent, PositionTrackerAgent, and HistoryAgent

Expose:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Primary skill:

- `WalletAgent`: `okx-agentic-wallet`
- `PositionTrackerAgent`: `okx-dex-market`
- `HistoryAgent`: `okx-dex-market`

Do not expose unrestricted trade execution tools in generic command flows.

## 8.5 Execution Tools

Execution tools should be exposed only to a bounded `Swap Execution Agent` after policy checks pass.

That means:

- the graph node decides whether execution is allowed,
- the model does not get an open-ended choice to bypass safety steps,
- every execution call happens with validated inputs,
- persistence and idempotency remain outside the agent in deterministic nodes.

## 9. LangChain Implementation Pattern

## 9.1 Base Agent Construction

Use `create_agent(...)` for each bounded agent role:

- one parsing agent,
- one enrichment agent,
- one decision agent,
- one exit agent,
- one swap execution agent.

Each agent should have:

- a role-specific prompt,
- a narrow tool set,
- a typed output schema,
- middleware for prompt shaping and tool filtering,
- checkpointer-backed execution via LangGraph.

For OKX integrations, the default should be:

- progressive disclosure through skill-loading tools,
- generic `onchainos` command tools for live OKX-covered capabilities,
- app-owned tools only for non-OKX capabilities.

## 9.2 Runtime Context

Use LangChain runtime context for static per-run dependencies:

- `user_id`
- `bot_id`
- `source_channel_id`
- `signal_id`
- `position_id`
- environment flags
- DB/session handles via service container references

Runtime context should not be used as the main business persistence layer.

## 9.3 Middleware

Use middleware for:

- dynamic prompts based on action type,
- filtering tools based on graph stage,
- logging model call metadata,
- attaching risk policy instructions,
- selecting smaller vs stronger model variants when needed.

## 10. Recommended Model Strategy

Use at least two model profiles:

- `fast_model` for parsing, summarization, and low-risk extraction
- `strong_model` for final decision synthesis on ambiguous signals

Example policy:

- signal classification -> fast model
- trade decision with incomplete or conflicting evidence -> strong model
- Telegram summary generation -> fast model

This follows the LangChain middleware pattern for dynamic model selection.

## 11. Structured Output Contract

Every model-facing critical step should produce structured output.

### 11.1 Parsing Agent Output

```text
message_type
is_trade_call
raw_symbol
raw_contract_address
raw_chain_hint
entry_reference
target_reference
stop_reference
urgency
confidence
reasoning_summary
```

### 11.2 Decision Agent Output

```text
decision: execute | skip | block
side: buy | none
confidence
trade_rationale
risk_summary
sizing_recommendation
required_policy_checks
telegram_summary
```

### 11.3 Exit Agent Output

```text
decision: hold | exit_hard | exit_trailing_arm | exit_trailing_fire
exit_reason
confidence
telegram_summary
```

## 12. Deterministic Policy Gates

These rules must live outside the model:

- wallet logged in
- chain supported
- sufficient balance on target execution chain
- token resolved exactly when the regular-token lane requires it
- token risk scan passed for the regular-token lane
- quote exists
- price impact <= hard cap
- trade size <= configured max risk
- active position count <= limit
- chain exposure <= limit

If any hard gate fails, execution stops regardless of model recommendation.

## 13. Fault Tolerance

Use LangGraph persistence with `thread_id` for:

- recovery after process crash,
- replay of failed runs,
- auditability of state transitions,
- idempotent resume behavior.

Thread examples:

- `signal:<signal_id>`
- `position:<position_id>`
- `command:<telegram_chat_id>:<message_id>`

## 14. Observability

Use LangSmith traces for:

- per-node latency,
- model/tool call visibility,
- failure localization,
- evaluation of parsing and decision quality.

Keep application audit tables as the business source of truth for trade history.
