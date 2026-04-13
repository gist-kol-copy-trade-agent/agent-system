# Implementation Plan

## Purpose

This folder contains the implementation plan for turning the current product and architecture docs into code.

Structure:

- `README.md`: phase overview and execution order
- one file per implementation phase

## Phase Overview

### Phase 1

- [phase-1-foundation-and-contracts.md](phase-1-foundation-and-contracts.md)
- Goal: scaffold the codebase, define executable schemas/config, and implement the persistence foundation

### Phase 2

- [phase-2-integrations-and-commands.md](phase-2-integrations-and-commands.md)
- Goal: implement Telegram command handling, scraper integration, and user strategy profile flows

### Phase 3

- [phase-3-signal-intake-and-trade-decision.md](phase-3-signal-intake-and-trade-decision.md)
- Goal: implement the signal pipeline from webhook event to policy-gated trade execution

### Phase 4

- [phase-4-position-monitoring-and-hardening.md](phase-4-position-monitoring-and-hardening.md)
- Goal: implement exit monitoring, reliability controls, and production-grade observability/hardening for the PoC

## Recommended Execution Order

1. complete Phase 1 before parallelizing anything else
2. complete core pieces of Phase 2 before Phase 3
3. Phase 3 is the first end-to-end trading milestone
4. Phase 4 closes the PoC loop and prepares the system for stable demo operation

## Reference Set

The implementation plan is derived from:

- [../prd-official.md](../prd-official.md)
- [../okx-skill-mapping.md](../okx-skill-mapping.md)
- [../architecture/README.md](../architecture/README.md)

The phase files link to the exact architecture docs they depend on.
