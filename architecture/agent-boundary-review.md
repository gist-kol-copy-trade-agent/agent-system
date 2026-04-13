# Agent Boundary Review

This note reviews the current agent split against LangChain and LangGraph guidance.

Primary references:

- `langchain/multi-agent/index`
- `langchain/multi-agent/skills`
- `langgraph/thinking-in-langgraph`
- `langgraph/workflows-agents`

## Core Principle

LangGraph encourages small workflow nodes for resilience, observability, and retry isolation.

That does **not** mean every node must become a separate agent.

The practical rule for this codebase is:

- use a separate **agent** when a step has distinct reasoning behavior, tool surface, context boundary, or safety boundary
- use a plain **deterministic node** when a step is mostly transformation, validation, persistence, or execution control
- prefer a **single agent + skills** over multiple agents when the task is still one coherent reasoning domain and does not need strong sequencing boundaries

## Current Assessment

| Agent | Current Role | Why Separate Today | Could Merge Later? | Recommendation |
| --- | --- | --- | --- | --- |
| `ParsingAgent` | Parse raw message into structured signal clues | Distinct language-understanding step, narrow output schema, dedicated OKX token clue lookup | Low | Keep separate |
| `EnrichmentAgent` | Gather entry wallet/market/risk context | Uses OKX skills and read-only commands to build entry decision inputs | Low | Keep separate |
| `DecisionAgent` | Convert enriched entry context into buy/skip/block decision | Pure reasoning step with no OKX reads; safety boundary is clear | Low | Keep separate |
| `ExitEnrichmentAgent` | Refresh exit market context before reevaluation | Exit context is different from entry context; narrower market-only role | Medium | Keep separate for now |
| `ExitAgent` | Convert exit context into hold/hard/trailing decision | Distinct reasoning contract and output schema | Low | Keep separate |
| `SwapExecutionAgent` | Turn approved intent into skill-guided swap execution | Separate mutating safety boundary; skill-guided execution is distinct from decisioning | Low | Keep separate |
| `WalletCommandAgent` | Read-only wallet/status/portfolio/history responses | Wallet domain agent, but tool surface overlaps onboarding | Medium | Consider merge later with wallet domain agent |
| `WalletOnboardingAgent` | Email/OTP wallet onboarding | Multi-turn auth flow and mutating wallet actions justify a separate boundary today | Medium | Keep separate for now |
| `TradeStyleOverrideAgent` | Parse free-form settings overrides into structured patch | Very small bounded parser; no external actions | Medium | Keep, but could be absorbed into a generic settings parser later |
| `FollowProfilingAgent` | Analyze historical channel calls and propose conviction | Distinct retrospective analysis domain with different prompt/output | Low | Keep separate |

## Where The Current Design Matches Docs

- The system uses **LangGraph workflows** for deterministic sequencing and checkpoint boundaries.
- The system uses **agents only at reasoning-heavy steps**.
- The system uses **skills** to keep OKX domain knowledge prompt-driven and loaded on demand.
- Deterministic nodes still own:
  - validation
  - persistence
  - policy gates
  - workflow routing
  - idempotency

This is consistent with LangGraph's workflow guidance and LangChain's skills pattern.

## Where To Watch For Over-Segmentation

An agent split should be reconsidered if most of these are true:

- the tool set is nearly identical to another agent
- the context schema is mostly duplicated
- the prompt differs only slightly
- the agent is not reused outside a single narrow step
- there is no safety or policy boundary that requires isolation

If those conditions hold, a single agent with skills or a simpler deterministic step may be better.

## MVP Guidance

For MVP V1, the current split is acceptable.

Reasons:

- it keeps prompts narrow
- it makes testing easier
- it maps cleanly to workflow milestones
- it isolates mutating execution from reasoning

The main domain to revisit later is the **wallet domain**:

- `WalletCommandAgent`
- `WalletOnboardingAgent`

These may eventually become a single wallet domain agent plus stateful workflow routing around it.

## Refactor Trigger

Refactor only if one of these becomes painful:

- model call cost or latency grows too much
- prompts drift and become hard to maintain consistently
- tool binding duplication causes bugs
- a new feature needs to reuse the same reasoning domain across several flows

Until then, keep the current split and avoid premature consolidation.
