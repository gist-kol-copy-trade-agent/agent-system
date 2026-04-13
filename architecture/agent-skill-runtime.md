# Agent Skill Runtime

## Purpose

This document shows how the model-facing agents load OKX skills at runtime, when they do it, and how those skill prompts connect to `onchainos` command execution and structured outputs.

The important rule is:

- the application does not preload OKX skill text into prompts,
- the agent decides when to call `load_okx_skill(...)`,
- the skill text is loaded on demand from `okx-onchainos-skills/`,
- the agent then follows that skill guidance through bounded tools.

## Shared Runtime Pattern

```mermaid
flowchart LR
    A[LangGraph Node] --> B[LangChain Agent invoke]
    B --> C{Need OKX capability?}
    C -- No --> D[Reason on provided context]
    C -- Yes --> E[load_okx_skill]
    E --> F[OKXSkillRegistry.load_skill]
    F --> G[Read SKILL.md from okx-onchainos-skills]
    G --> H[Skill prompt returned to agent]
    H --> I{Need more detail?}
    I -- Yes --> J[load_okx_skill_reference]
    J --> K[Read reference file inside skill folder]
    I -- No --> L[Call bounded tool]
    K --> L
    L --> M[run_onchainos_readonly or run_onchainos_mutating_swap]
    M --> N[Local onchainos CLI on server]
    N --> O[Tool result returned to agent]
    O --> P[Structured output]
    D --> P
```

## Parsing Agent

When to load skill:

- when token identity is ambiguous,
- when the message has incomplete token clues,
- when the parser needs to resolve symbol / chain / contract hints before downstream steps.

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Expected OKX skills:

- `okx-dex-token`
- optionally `okx-dex-market`

```mermaid
flowchart TD
    A[Signal Intake Graph: parse_signal] --> B[ParsingAgent.invoke]
    B --> C[Parse raw message]
    C --> D{Token clues sufficient?}
    D -- Yes --> E[Return ParsedSignal]
    D -- No --> F[load_okx_skill okx-dex-token]
    F --> G[Read SKILL.md]
    G --> H[run_onchainos_readonly token search or token info]
    H --> I[Resolve best token clue set]
    I --> E
```

Structured output produced:

- message classification,
- raw symbol / CA / chain hints,
- resolved symbol / contract / chain,
- optional token name and decimals.

## Enrichment Agent

When to load skill:

- after parsing and lane classification,
- before decision,
- to gather all external OKX-covered decision inputs.

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Expected OKX skills:

- `okx-agentic-wallet`
- `okx-dex-market`
- `okx-security`
- `okx-dex-token`
- `okx-dex-swap` when quote context is needed

```mermaid
flowchart TD
    A[Signal Intake Graph: enrich_context] --> B[EnrichmentAgent.invoke]
    B --> C[Load parsed signal and resolved asset]
    C --> D[load_okx_skill okx-agentic-wallet]
    D --> E[run_onchainos_readonly wallet status or balance]
    C --> F[load_okx_skill okx-dex-market]
    F --> G[run_onchainos_readonly market price or kline]
    C --> H{Regular token lane?}
    H -- Yes --> I[load_okx_skill okx-security or okx-dex-token]
    I --> J[run_onchainos_readonly security token-scan or token advanced-info]
    H -- No --> K[Skip regular-token risk scan]
    E --> L[Normalize wallet snapshot]
    G --> M[Normalize market snapshot]
    J --> N[Normalize risk snapshot]
    K --> N
    L --> O[Return EnrichmentOutput]
    M --> O
    N --> O
```

Structured output produced:

- `wallet_snapshot`
- `market_snapshot`
- `risk_snapshot`
- optional `signal_overlay`

## Decision Agent

When to load skill:

- never in the current design.

This agent is intentionally pure reasoning after enrichment is complete.

Tools exposed:

- none

```mermaid
flowchart TD
    A[Signal Intake Graph: decision] --> B[DecisionAgent.invoke]
    B --> C[Receive parsed signal]
    B --> D[Receive resolved asset]
    B --> E[Receive wallet snapshot]
    B --> F[Receive market snapshot]
    B --> G[Receive risk snapshot]
    B --> H[Receive TA snapshot]
    B --> I[Receive strategy profile]
    C --> J[Reason only]
    D --> J
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[Return execute or skip or block]
```

## Wallet Agent

When to load skill:

- on `/start`,
- on `/status`.

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_readonly`

Expected OKX skills:

- always `okx-agentic-wallet`

```mermaid
flowchart TD
    A[WalletService] --> B[WalletAgent.invoke]
    B --> C[load_okx_skill okx-agentic-wallet]
    C --> D[run_onchainos_readonly wallet status or addresses]
    B --> E{Need login or verify?}
    E -- Yes --> F[run_onchainos_mutating_wallet]
    E -- No --> G[Skip mutation]
    D --> H[Return WalletAgentOutput]
    F --> H
    G --> H
```

## Exit Agent

When to load skill:

- optionally during exit reasoning,
- but not for execution.

Current design keeps exit reasoning primarily on normalized position, market, and deterministic TA snapshots. Skill-loading remains available in case exit reasoning later needs deeper market guidance, but the agent does not directly execute trades.

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `get_position_snapshot`
- `get_token_market_snapshot`
- `compute_exit_ta_score`

```mermaid
flowchart TD
    A[Exit Graph: exit_decision] --> B[ExitAgent.invoke]
    B --> C[get_position_snapshot]
    B --> D[get_token_market_snapshot]
    B --> E[compute_exit_ta_score]
    B --> F{Need additional OKX guidance?}
    F -- Yes --> G[load_okx_skill okx-dex-market]
    F -- No --> H[Reason on normalized inputs]
    G --> H
    H --> I[Return hold or exit_hard or exit_trailing_arm or exit_trailing_fire]
```

## Swap Execution Agent

When to load skill:

- only after deterministic policy approval,
- only for validated buy or sell intent,
- only inside execution nodes.

Tools exposed:

- `load_okx_skill`
- `load_okx_skill_reference`
- `run_onchainos_mutating_swap`

Expected OKX skill:

- `okx-dex-swap`

```mermaid
flowchart TD
    A[Policy Gate Passed] --> B[SwapExecutionAgent.invoke]
    B --> C[Receive validated intent]
    C --> D[load_okx_skill okx-dex-swap]
    D --> E[Read swap skill prompt]
    E --> F[run_onchainos_mutating_swap]
    F --> G[Local onchainos swap execute]
    G --> H[Execution result]
    H --> I[Return execution_request and execution_result]
    I --> J[Deterministic persistence and idempotency node]
```

## Boundary Summary

```mermaid
flowchart LR
    A[Parsing Agent] -->|may load skill| B[OnchainOS Read Tools]
    C[Enrichment Agent] -->|may load skill| B
    D[Wallet Command Agent] -->|may load skill| B
    E[Decision Agent] -->|no skill loading| F[Pure reasoning only]
    G[Exit Agent] -->|optional skill guidance, no execution| H[Read-only normalized tools]
    I[Swap Execution Agent] -->|must load okx-dex-swap| J[Mutating swap tool]
    J --> K[Deterministic persistence outside agent]
```

## Implementation Mapping

The runtime pieces that make this work are:

- skill registry:
  - `system/app/services/okx_skills.py`
- agent-bound tools:
  - `system/app/tools/langchain_agent_tools.py`
- model-backed agent construction:
  - `system/app/agents/parsing.py`
  - `system/app/agents/enrichment.py`
  - `system/app/agents/decision.py`
  - `system/app/agents/wallet_command.py`
  - `system/app/agents/exit.py`
  - `system/app/agents/swap_execution.py`
