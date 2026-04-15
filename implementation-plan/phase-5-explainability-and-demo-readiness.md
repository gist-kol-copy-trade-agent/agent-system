# Phase 5: Explainability and Demo Readiness

## Status

Implemented for MVP v1.

Implemented scope:

- explanation artifacts promoted to first-class graph state
- `DecisionAgent`, `EnrichmentAgent`, `FollowProfilingAgent`, `ExitAgent`, and `SwapExecutionAgent` extended with richer explanation / receipt fields
- deterministic notification renderer switched from hard-coded stage templates to structured explanation-aware rendering
- notification rendering mode added: `compact`, `standard`, `demo_longform`
- explanation payloads persisted into `telegram_notifications`
- workflow-level explainability snapshots persisted into `workflow_runs.run_metadata`

Remaining intentional MVP limits:

- no separate explanation-specific DB table; reuse existing notification and workflow persistence
- no additional model-based narration node; long-form output remains renderer-driven from structured artifacts
- `ta_explanation`, `policy_explanation`, and `exit_ta_explanation` are scaffolded in state but not yet fully produced by dedicated agent/schema work
- replay/audit views are persisted but not yet exposed via dedicated UI or Telegram commands

## Goal

Close the gap between the current runtime and the scripted demo expectations by making the system able to surface richer reasoning, analysis, and execution receipts to the user without weakening deterministic safety boundaries.

This phase is not about adding new trading capabilities.
It is about making the existing capabilities legible and demo-quality.

## Detailed Plan

## 1. Introduce Explanation Artifacts as First-Class Outputs

Extend agent outputs so the system has structured explanation objects, not only compact action summaries.

Add richer user-facing fields for:

- `DecisionAgent`
- `EnrichmentAgent`
- `ExitAgent`
- `FollowProfilingAgent`
- `SwapExecutionAgent`

These fields should distinguish:

- machine-oriented decision state,
- user-facing reasoning state,
- final Telegram-ready explanation fragments.

The explanation layer should remain structured, not free-form raw text only.

## 2. Expand Decision-Agent Output

Extend the trade-decision schema beyond:

- `decision`
- `decision_reason_code`
- `confidence`
- `rationale_summary`
- `telegram_summary`

Add fields such as:

- `analysis_thesis`
- `ta_reasoning`
- `risk_reasoning`
- `sizing_reasoning`
- `policy_expectation_summary`
- `user_message_long`

The decision agent should be able to justify:

- why the setup is constructive or not,
- how TA contributes,
- how wallet balance and strategy profile cap sizing,
- why the lane-specific logic is satisfied or not.

## 3. Expand Enrichment-Agent Output

Keep normalized snapshots for policy and execution, but add richer analysis-ready explanation fields.

Add fields such as:

- `wallet_summary`
- `market_summary`
- `risk_summary_long`
- `overlay_summary_long`
- `evidence_points`

This should support demo-quality context messages such as:

- why the market is trending,
- why liquidity and quote quality are acceptable,
- why a token scan is clean or risky,
- what smart-money / KOL overlays imply.

## 4. Expand Follow-Profiling Output

Extend the follow-profiling schema and rendering to better match the retrospective demo story.

Add fields such as:

- `biggest_win_symbol`
- `biggest_win_return_pct`
- `major_asset_bias`
- `regular_token_bias`
- `pattern_breakdown`
- `user_message_long`

The profiling result should be able to explain:

- the strongest historical winner,
- whether the channel is better on majors or regular tokens,
- what quality patterns were found in the sampled messages.

## 5. Expand Exit-Agent Output

Extend the exit-decision schema beyond a compact `telegram_summary`.

Add fields such as:

- `trigger_reasoning`
- `trailing_plan`
- `risk_protection_summary`
- `user_message_long`

This should support demo-quality exit narration such as:

- why the bot is holding,
- why trailing was armed,
- why a hard exit was selected,
- how stop-loss / take-profit / trailing defaults interact.

## 6. Expand Swap Execution Receipt

Extend execution outputs and final Telegram rendering for both entry and exit.

Add fields such as:

- `explorer_url`
- `approval_explorer_url`
- `execution_price`
- `effective_price_impact_pct`
- `route_summary`
- `receipt_message_long`

The runtime should be able to render a demo-quality execution receipt with:

- tx hashes,
- explorer links,
- amount out,
- effective fill price,
- price impact,
- approval transaction details when present.

## 7. Replace Hard-Coded Progress Templates with Structured Renderers

Current progress notifications are mostly deterministic, shallow templates.

Replace this with a two-layer model:

1. graph/agent nodes produce structured explanation artifacts
2. deterministic renderers format those artifacts into Telegram messages

Do not make notification rendering a mandatory new model node by default.
The renderer layer should stay deterministic for MVP stability.

## 8. Add Optional Long-Form Narrative Messages Between Core Steps

Support a richer demo mode without changing the execution boundary.

For selected stages:

- enrichment ready
- TA ready
- decision drafted
- execution submitted
- follow profile ready
- exit decision drafted

allow the system to emit:

- short status card,
- optional long-form analyst-style reasoning block.

This should be configuration-driven so demo mode can be enabled without making normal operation excessively verbose.

## 9. Persist Explanation Artifacts

Persist explainability payloads with workflow and notification records so the system can:

- replay demo flows,
- inspect why the bot acted,
- debug reasoning quality after the run,
- support richer `/history` or future audit views.

Do not persist arbitrary chain-of-thought text.
Persist only the structured explanation artifacts intentionally designed for user display and auditability.

## 10. Optional Architecture Enhancement: Explanation Layer

Document an explicit explainability layer in architecture:

- not a separate execution authority,
- not a replacement for policy,
- not a replacement for the underlying agent outputs,
- only a transformation layer from structured reasoning artifacts to user-facing narration.

This layer should sit after agent reasoning and before Telegram delivery.

## Acceptance Criteria

- the signal-intake pipeline can emit a richer context-ready message with factual details and interpretive summary
- the decision step can emit a multi-sentence rationale covering TA, risk, and sizing
- the `/follow` retrospective result can show more than aggregate metrics, including strongest pattern highlights
- entry execution receipts can include explorer links and richer fill details
- exit decision output can explain trailing / hard-exit reasoning in user-facing terms
- graph safety boundaries remain unchanged:
  - deterministic policy gate still decides final permission
  - execution still occurs only after policy approval
  - explainability fields do not change trading state on their own
- explanation artifacts are persisted in a structured way suitable for replay and audit
- the scripted demo in `demo-video-plan.md` can be produced with minimal manual embellishment

## Implementation Notes

This phase was implemented incrementally in the runtime with verification after each block:

1. first-class explanation artifacts in graph state and schema foundations
2. richer `DecisionAgent` output plus `decision_explanation`
3. richer `EnrichmentAgent` output plus `enrichment_explanation`
4. richer `FollowProfilingAgent` output and follow-profile rendering
5. richer `ExitAgent` output plus `exit_decision_explanation`
6. richer swap execution receipts for buy and sell flows
7. structured notification renderer consuming explanation artifacts
8. mode-driven long-form notification rendering
9. persistence of explanation payloads into notifications and workflow metadata

## References

- [../demo-video-plan.md](../demo-video-plan.md)
- [../architecture/action-flows.md](../architecture/action-flows.md)
- [../architecture/runtime-graph-charts.md](../architecture/runtime-graph-charts.md)
- [../architecture/core-agent-architecture.md](../architecture/core-agent-architecture.md)
- [../architecture/agent-skill-runtime.md](../architecture/agent-skill-runtime.md)
- [../architecture/domain-schemas.md](../architecture/domain-schemas.md)
- [../architecture/persistence-schema.md](../architecture/persistence-schema.md)
- [../architecture/state-and-persistence.md](../architecture/state-and-persistence.md)
