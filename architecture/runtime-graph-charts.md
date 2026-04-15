# Runtime Graph Charts

## Purpose

This document gives two implementation-facing Mermaid charts for the main runtime pipelines:

- signal intake -> follow trade execution
- scheduled exit evaluation -> exit execution

For each node, the chart shows:

- whether the node is deterministic or model-driven,
- which LangChain agent is used,
- which tools are exposed,
- which OKX OnchainOS skills the model is expected to load,
- which default model is configured today.

## Model Defaults

- `ParsingAgent` -> `openai:gpt-5.3-mini`
- `EnrichmentAgent` -> `openai:gpt-5.4`
- `DecisionAgent` -> `openai:gpt-5.4`
- `PositionTrackerAgent` -> `openai:gpt-5.3-mini`
- `ExitAgent` -> `openai:gpt-5.4`
- `SwapExecutionAgent` -> `openai:gpt-5.4`

## 1. Signal Intake and Follow Trade Pipeline

```mermaid
flowchart TD
    A["ingest_signal<br/>Deterministic<br/>Input: webhook payload -> graph state"] --> B
    B["parse_signal<br/>Model: ParsingAgent<br/>Model: openai:gpt-5.3-mini<br/>Tools: load_okx_skill, load_okx_skill_reference, run_onchainos_readonly<br/>Skills: okx-dex-token, optional okx-dex-market<br/>Output: ParsedSignal"] --> C
    C{"parse actionable?"}
    C -- "no" --> Z1["END<br/>Skip non-actionable signal"]
    C -- "yes" --> D
    D["classify_asset_lane<br/>Deterministic<br/>BTC ETH SOL -> major<br/>else -> regular"] --> E
    E["resolve_target_asset<br/>Deterministic<br/>Major: map to X Layer representation<br/>Regular: validate token clues or block unresolved"] --> F
    F{"resolved enough?"}
    F -- "no" --> Z2["END<br/>Blocked: TOKEN_UNRESOLVED"]
    F -- "yes" --> G
    G["load_strategy_profile<br/>Deterministic<br/>Load global user strategy settings"] --> H
    H["enrich_context<br/>Model: EnrichmentAgent<br/>Model: openai:gpt-5.4<br/>Tools: load_okx_skill, load_okx_skill_reference, run_onchainos_readonly<br/>Skills: okx-agentic-wallet, okx-dex-market, okx-security, okx-dex-token, optional okx-dex-swap for quote context<br/>Output: wallet_snapshot, market_snapshot, risk_snapshot, signal_overlay"] --> I
    I{"market kline available?"}
    I -- "no" --> Z3["END<br/>Blocked: MARKET_KLINE_MISSING"]
    I -- "yes" --> J
    J["compute_ta<br/>Deterministic<br/>Tool: compute_ta_score<br/>Input: market_snapshot.kline_window + liquidity + strategy limits<br/>Output: TA snapshot"] --> K
    K["decision<br/>Model: DecisionAgent<br/>Model: openai:gpt-5.4<br/>Tools: none<br/>Skills: none loaded here<br/>Input: parsed + resolved + wallet + market + risk + TA + strategy<br/>Output: execute | skip | block"] --> L
    L["apply_policy_gate<br/>Deterministic<br/>Checks: wallet readiness, risk gate, quote gate, slippage, amount cap, active positions, lane rules"] --> M
    M{"policy action == execute?"}
    M -- "no" --> Z4["END<br/>Skip or block after policy"]
    M -- "yes" --> N
    N["execute_trade<br/>Model: SwapExecutionAgent<br/>Model: openai:gpt-5.4<br/>Tools: load_okx_skill, load_okx_skill_reference, run_onchainos_readonly, run_onchainos_mutating_swap<br/>Skills: okx-dex-swap, optional okx-agentic-wallet fallback for wallet resolution<br/>Output: execution_request + execution_result"] --> O
    O["persist_trade_result<br/>Deterministic<br/>Persist execution, create/open position, write position events"] --> Z5["END"]
```

## 2. Exit Pipeline

```mermaid
flowchart TD
    A["load_position<br/>Deterministic<br/>Input: cron-selected open position + trailing state"] --> B
    B["load_strategy_profile<br/>Deterministic<br/>Load global user strategy settings"] --> C
    C["load_market_context<br/>Model: PositionTrackerAgent<br/>Model: openai:gpt-5.3-mini<br/>Tools: load_okx_skill, load_okx_skill_reference, run_onchainos_readonly<br/>Skills: okx-dex-market, optional okx-agentic-wallet fallback for wallet resolution<br/>Output: position_tracking_snapshot + exit_market_snapshot"] --> D
    D["compute_exit_ta<br/>Deterministic<br/>Compute PnL, peak, drawdown, hard-stop, take-profit, trailing-arm, trailing-fire, max-hold triggers"] --> E
    E["build_exit_inputs<br/>Deterministic<br/>Assemble exit context + pre-summary"] --> F
    F["exit_decision<br/>Model: ExitAgent<br/>Model: openai:gpt-5.4<br/>Tools: load_okx_skill, load_okx_skill_reference, get_position_snapshot, get_token_market_snapshot, compute_exit_ta_score<br/>Skills: normally none required; optional okx-dex-market guidance remains available<br/>Output: hold | exit_hard | exit_trailing_arm | exit_trailing_fire"] --> G
    G["apply_exit_policy_gate<br/>Deterministic<br/>Map decision into hold | persist_trailing | execute | block"] --> H
    H{"policy action"}
    H -- "hold / persist_trailing / block" --> I
    H -- "execute" --> J
    I["persist_evaluation<br/>Deterministic<br/>Persist exit evaluation, update trailing state, refresh position marks"] --> Z1["END"]
    J["execute_exit<br/>Model: SwapExecutionAgent<br/>Model: openai:gpt-5.4<br/>Tools: load_okx_skill, load_okx_skill_reference, run_onchainos_readonly, run_onchainos_mutating_swap<br/>Skills: okx-dex-swap, optional okx-agentic-wallet fallback for wallet resolution<br/>Output: execution_request + execution_result"] --> K
    K["persist_exit_result<br/>Deterministic<br/>Persist sell execution, close position, write position events, store realized result"] --> Z2["END"]
```

## Reading Notes

- `ParsingAgent` is the only model node allowed to interpret raw Telegram language in the entry pipeline.
- `EnrichmentAgent` is the node that should gather OKX-covered external context, including wallet state, market data, kline data, and regular-token risk inputs.
- `DecisionAgent` is intentionally pure reasoning on already-collected data and does not call OKX tools.
- `PositionTrackerAgent` is the model node that refreshes live position and wallet PnL context for exit evaluation.
- `SwapExecutionAgent` is the only model node allowed to invoke bounded mutating swap execution, and only after deterministic policy approval.
