# Explainability Layer

## Purpose

This document defines the explainability layer that sits between:

- model or deterministic reasoning outputs,
- Telegram-facing user communication,
- and audit-ready persisted explanation artifacts.

The goal is to let the system explain itself clearly in Telegram without weakening the core safety model.

This layer must not become:

- a hidden policy override,
- a second execution authority,
- or a place where free-form chain-of-thought is stored.

## Design Goal

The system already has three strong properties:

- bounded model nodes,
- deterministic policy gates,
- deterministic persistence and execution control.

What is missing is a first-class way to expose:

- why a setup is good or bad,
- what data was gathered,
- how sizing was decided,
- why an exit triggered,
- and what exactly happened during execution.

The explainability layer solves that gap.

## Core Principle

Separate these three concerns:

1. machine decision state
2. user-facing explanation artifacts
3. final Telegram rendering

They are related, but they should not be collapsed into one string field.

## Layer Position in Runtime

Recommended sequence:

1. graph node computes or agent returns business state
2. graph node or agent also emits structured explanation artifacts
3. deterministic renderer formats those artifacts for Telegram
4. notification service sends the final message
5. structured artifacts are persisted for replay and audit

This means:

- the model still reasons in the bounded agent node,
- the deterministic graph still owns control flow,
- the explainability layer only transforms and exposes already-approved reasoning outputs.

## What the Layer Must Not Do

The explainability layer must not:

- decide whether a trade executes,
- modify `execute | skip | block`,
- alter execution amount after policy gate,
- bypass deterministic hard blocks,
- invoke mutating OKX tools,
- persist arbitrary hidden chain-of-thought.

## Explanation Artifact Types

Recommended artifact families:

### 1. Parse Explanation

Purpose:

- explain what the parser extracted,
- explain confidence and unresolved ambiguity.

Examples:

- asset label selected
- message classified as trade call
- chain hint absent or present
- confidence rationale

### 2. Enrichment Explanation

Purpose:

- explain what external context was gathered,
- explain how market / wallet / risk data should be interpreted.

Examples:

- wallet readiness summary
- market quality summary
- risk interpretation summary
- smart-money / KOL overlay summary
- evidence points

### 3. TA Explanation

Purpose:

- explain deterministic TA outputs in user-facing language.

Examples:

- momentum interpretation
- volatility interpretation
- liquidity gate explanation
- composite TA explanation

### 4. Decision Explanation

Purpose:

- explain why a trade was selected, skipped, or blocked.

Examples:

- thesis
- TA reasoning
- risk reasoning
- sizing reasoning
- final recommendation summary

### 5. Policy Explanation

Purpose:

- explain deterministic pass/fail and constraint enforcement.

Examples:

- which hard checks passed
- which caps limited size
- which failure codes caused a block

### 6. Execution Receipt Explanation

Purpose:

- explain what happened during buy or sell execution.

Examples:

- tx hash
- explorer link
- fill amount
- effective execution price
- price impact
- approval details when applicable

### 7. Exit Explanation

Purpose:

- explain why a position is held, armed for trailing, or exited.

Examples:

- trigger reasoning
- trailing plan
- stop-loss or take-profit explanation
- risk protection summary

### 8. Follow Profiling Explanation

Purpose:

- explain why a channel is worth following or not.

Examples:

- strongest historical pattern
- biggest historical winner
- major-vs-regular bias
- conviction rationale

## Recommended Schema Direction

Business schemas should keep compact machine fields.

Alongside them, add explicit explanation objects such as:

```python
class ExplanationArtifact(TypedDict):
    title: str
    summary: str
    evidence_points: list[str]
    key_metrics: dict[str, str | float | int | bool | None]
    long_form_message: str | None
```

Then specialize per stage:

- `ParseExplanation`
- `EnrichmentExplanation`
- `DecisionExplanation`
- `PolicyExplanation`
- `ExecutionReceiptExplanation`
- `ExitExplanation`
- `FollowProfileExplanation`

Important:

- these are user-display artifacts,
- they are not hidden reasoning transcripts,
- they should be safe to store and replay.

## Rendering Strategy

Use a deterministic renderer by default.

Why:

- predictable user-facing output,
- stable formatting,
- easier testing,
- no extra model latency,
- no risk that the renderer changes the semantics of the decision.

Recommended rendering model:

1. compact card
2. optional long-form analyst note

This allows:

- concise operation in normal mode,
- richer narration when the operator wants more detail.

## Rendering Modes

Introduce a configuration-controlled explainability mode.

Suggested modes:

- `compact`
- `standard`
- `longform`

Behavior:

- `compact`: short progress cards only
- `standard`: short cards + moderate summaries
- `longform`: short cards + long-form analyst explanations + richer receipts

The mode should affect rendering only.
It should not change policy or execution behavior.

## Persistence Policy

Persist explanation artifacts in the application DB, not only ephemeral graph state.

Good persistence targets:

- workflow run metadata
- notification records
- decision / execution / exit audit payloads

Current MVP implementation direction:

- `workflow_runs.run_metadata_json` stores `execution_trace`, selected explanation artifacts, and final decision / execution snapshots
- `telegram_notifications.explanation_json` stores the explanation payload used to render each notification

Do not persist:

- unrestricted hidden model reasoning,
- raw chain-of-thought,
- prompt internals unless explicitly needed for debugging and separately governed.

## Integration with Existing Graphs

### Signal Intake Graph

Recommended additions:

- `parse_explanation`
- `enrichment_explanation`
- `ta_explanation`
- `decision_explanation`
- `policy_explanation`
- `execution_receipt_explanation`

### Exit Graph

Recommended additions:

- `position_tracking_explanation`
- `exit_ta_explanation`
- `exit_decision_explanation`
- `exit_policy_explanation`
- `exit_execution_receipt_explanation`

### Follow Profiling Flow

Recommended additions:

- `follow_profile_explanation`

## Why This Is an Architecture Change

This is not only a prompt tweak.

Without an explicit explainability layer:

- every stage compresses into one short summary string,
- Telegram output quality depends on hard-coded templates,
- richer long-form Telegram narration requires additional manual formatting effort,
- future replay / audit views stay too weak.

With the explainability layer:

- reasoning becomes part of the system design,
- explanation quality can improve without touching safety boundaries,
- user-facing clarity and auditability improve together.

## Acceptance Standard

This layer is correctly implemented only if:

- user-facing reasoning becomes richer,
- deterministic policy and execution boundaries remain unchanged,
- explanation artifacts are structured and persistable,
- rendering is testable and mode-driven,
- real runtime outputs are clear enough to follow without extra operator narration.

## References

- [action-flows.md](action-flows.md)
- [runtime-graph-charts.md](runtime-graph-charts.md)
- [domain-schemas.md](domain-schemas.md)
- [state-and-persistence.md](state-and-persistence.md)
- [../implementation-plan/phase-5-explainability-and-telegram-ux-quality.md](../implementation-plan/phase-5-explainability-and-telegram-ux-quality.md)
