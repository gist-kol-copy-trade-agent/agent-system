# Design Principles

## 1. Core Principle

The architecture follows this division of responsibility:

- LangChain is the foundation layer.
- LangGraph is the orchestration and state-management layer.

This is the main design rule for the project.

## 2. LangChain as the Foundation

Use LangChain for the reusable AI building blocks that almost every intelligent workflow needs:

- model integration,
- prompt construction,
- tool definitions,
- structured output,
- middleware,
- agent construction via `create_agent`.

In this project, LangChain is responsible for the bounded reasoning units:

- Parsing Sub-Agent
- Decision Sub-Agent
- Exit Sub-Agent

LangChain should not be treated as the full workflow engine for the trading system.

## 3. LangGraph as the Control Brain

Use LangGraph when the system is no longer a simple linear flow and needs explicit runtime control.

LangGraph is the correct layer for:

- loops,
- branching,
- stateful workflows,
- checkpointing,
- thread-scoped memory,
- recovery and replay,
- durable execution,
- deterministic policy gates around model calls.

In this project, LangGraph is responsible for:

- signal intake workflow,
- trade decision workflow,
- trade execution workflow,
- position monitoring workflow,
- exit workflow,
- command workflows,
- checkpoint-backed run recovery.

## 4. Practical Rule for This Project

The project should not be implemented in either of these extremes:

- not as a pure LangChain-only free-form agent,
- not as a fully low-level LangGraph-only system without LangChain abstractions.

Instead, the correct pattern is:

1. build bounded AI capabilities with LangChain,
2. place those capabilities inside LangGraph nodes,
3. use LangGraph to control state transitions, persistence boundaries, and execution safety.

## 5. Why This Principle Matters Here

The trading bot has all the characteristics that require LangGraph-level orchestration:

- non-linear flows,
- retries and recovery,
- action gating before execution,
- state that must survive failures,
- multiple action types with different tool access policies,
- scheduled monitoring and re-entry into workflows.

At the same time, it still benefits from LangChain abstractions for:

- model calls,
- tool calling,
- prompt management,
- structured agent outputs.

This rule also applies to OKX wallet capabilities:

- if a capability is primarily expressed through an OKX skill such as `okx-agentic-wallet`,
- the agent should load and use that skill through LangChain tool calls,
- not bypass it with app-specific deterministic wrappers as the primary interaction pattern.

## 6. Team Rule of Thumb

When adding a new capability, ask:

- Is this a model/tool reasoning capability?
  - Put it in LangChain.
- Is this a workflow, state, checkpoint, retry, or branching concern?
  - Put it in LangGraph.

If a step can move money, mutate positions, or change durable business state, it should be controlled by deterministic LangGraph nodes, not by an unrestricted agent loop.
