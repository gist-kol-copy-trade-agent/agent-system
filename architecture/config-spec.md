# Config Spec

## 1. Purpose

This document defines the runtime configuration surface for the PoC/V1 bot.

The goal is to keep:

- thresholds,
- policy knobs,
- preset defaults,
- integration settings,
- retry settings

out of prompts and out of hardcoded business logic.

## 2. Configuration Principles

- Config should be environment-aware.
- Product rules should live in config where practical.
- Prompts may describe policy, but config remains the executable source of truth.
- Risk thresholds must be adjustable without changing orchestration code.

## 3. Suggested Top-Level Structure

```yaml
environment:
models:
langgraph:
telegram:
scraper:
wallet:
execution:
strategy_presets:
policy:
risk_matrix:
monitoring:
observability:
```

## 4. Environment

```yaml
environment:
  name: development
  timezone: Asia/Ho_Chi_Minh
  default_locale: en-US
```

## 5. Models

```yaml
models:
  parsing_model: openai:gpt-5-mini
  decision_model: openai:gpt-5
  exit_model: openai:gpt-5-mini
  summary_model: openai:gpt-5-mini
  timeout_seconds: 30
  max_retries: 2
```

## 6. LangGraph Runtime

```yaml
langgraph:
  checkpointer_backend: postgres
  thread_prefix_signal: signal
  thread_prefix_position: position
  thread_prefix_command: command
  resume_on_restart: true
```

## 7. Telegram

```yaml
telegram:
  command_timeout_seconds: 15
  max_message_length: 4000
  default_notification_mode: concise
```

## 8. Scraper Integration

```yaml
scraper:
  register_endpoint: /register/channel_name
  unregister_endpoint: /unregister/channel_name
  webhook_endpoint: /webhooks/scraper/messages
  signature_header: X-Scraper-Signature
  timestamp_header: X-Scraper-Timestamp
  event_id_header: X-Event-Id
  replay_window_seconds: 300
  max_retry_attempts: 5
```

## 9. Wallet and Chain Policy

```yaml
wallet:
  major_execution_chain: xlayer
  major_assets:
    - BTC
    - ETH
    - SOL
  allow_cross_chain_funding: false
```

PoC/V1 note:

- `major_assets` is currently limited to `BTC`, `ETH`, and `SOL`
- the config structure is intentionally extensible so future versions can add assets such as `BNB` and `TRX` without changing the orchestration model

## 10. Execution Defaults

```yaml
execution:
  default_gas_level_major: average
  default_gas_level_regular: average
  enable_mev_protection_evm: true
  enable_mev_tips_solana: true
  min_trade_amount_usd:
    xlayer: 25
    ethereum: 25
    base: 25
    solana: 10
    default: 25
```

## 11. Strategy Presets

These are product defaults used by `/trade-style`.

```yaml
strategy_presets:
  safe:
    major_asset_lane_enabled: true
    regular_token_lane_enabled: true
    max_amount_per_trade_usd: 300
    max_portfolio_risk_pct_per_trade: 0.02
    max_active_positions: 3
    major_asset_max_amount_usd: 300
    regular_token_max_amount_usd: 100
    max_slippage_pct_major: 0.5
    max_slippage_pct_regular: 2.0
    max_price_deviation_pct_major: 2.0
    max_price_deviation_pct_regular: 3.0
    min_liquidity_usd_regular: 100000
    default_stop_loss_pct: 5.0
    default_take_profit_pct: 12.0
    max_holding_time_hours: 72

  normal:
    major_asset_lane_enabled: true
    regular_token_lane_enabled: true
    max_amount_per_trade_usd: 500
    max_portfolio_risk_pct_per_trade: 0.05
    max_active_positions: 5
    major_asset_max_amount_usd: 500
    regular_token_max_amount_usd: 200
    max_slippage_pct_major: 1.0
    max_slippage_pct_regular: 4.0
    max_price_deviation_pct_major: 3.0
    max_price_deviation_pct_regular: 5.0
    min_liquidity_usd_regular: 50000
    default_stop_loss_pct: 7.0
    default_take_profit_pct: 20.0
    max_holding_time_hours: 96

  degen:
    major_asset_lane_enabled: true
    regular_token_lane_enabled: true
    max_amount_per_trade_usd: 1000
    max_portfolio_risk_pct_per_trade: 0.10
    max_active_positions: 8
    major_asset_max_amount_usd: 1000
    regular_token_max_amount_usd: 400
    max_slippage_pct_major: 1.5
    max_slippage_pct_regular: 8.0
    max_price_deviation_pct_major: 5.0
    max_price_deviation_pct_regular: 8.0
    min_liquidity_usd_regular: 20000
    default_stop_loss_pct: 10.0
    default_take_profit_pct: 30.0
    max_holding_time_hours: 120
```

## 12. Policy Thresholds

```yaml
policy:
  min_source_score: 0.30
  min_ta_score_major: 0.50
  min_ta_score_regular: 0.60
  fail_closed_on_regular_token_risk_scan_error: true
  require_quote_before_execution: true
  block_if_price_impact_exceeds_user_limit: true
  block_if_active_positions_limit_reached: false
  skip_if_active_positions_limit_reached: true
```

## 13. Risk Matrix Thresholds

These thresholds back `risk-scoring-matrix.md`.

```yaml
risk_matrix:
  security:
    block_if_is_risk_token: true
    skip_if_buy_tax_pct_gt: 10
    skip_if_sell_tax_pct_gt: 10
    warn_if_buy_or_sell_tax_pct_gt: 5

  token_intelligence:
    block_if_dev_rug_pull_count_gte: 10
    skip_if_dev_rug_pull_count_gte: 1
    warn_if_dev_create_token_count_gte: 100

    block_if_top10_hold_percent_gte: 60
    skip_if_top10_hold_percent_gte: 35
    warn_if_top10_hold_percent_gte: 20

    skip_if_lp_burned_percent_lt: 50
    warn_if_lp_burned_percent_lt: 70

    adverse_tags:
      - suspiciousLiquidity
      - maliciousPattern
      - blacklistedProject

    positive_tags:
      - communityRecognized
      - smartMoneyBuy

    neutral_tags:
      - dexBoost
```

## 14. Scoring Weights

Optional explicit weights if the implementation uses weighted scoring:

```yaml
policy:
  scoring:
    source_score_weight_major: 0.4
    ta_score_weight_major: 0.6
    source_score_weight_regular: 0.3
    ta_score_weight_regular: 0.3
    token_risk_score_weight_regular: 0.4
```

## 15. Monitoring and Exit Defaults

```yaml
monitoring:
  position_refresh_interval_seconds: 60
  reevaluate_on_new_message: true
  reevaluate_on_price_update: false
  exit_priority:
    - hard_risk
    - kol_exit_signal
    - stop_loss
    - take_profit
    - trailing_stop
    - max_holding_time
```

## 16. Observability

```yaml
observability:
  enable_langsmith_tracing: true
  log_raw_webhook_payloads: true
  log_model_inputs: false
  log_model_outputs: true
  log_execution_requests: true
```

## 17. Config Ownership

Recommended ownership:

- product-level defaults -> version-controlled config
- environment-specific secrets -> secret manager / env vars
- user-specific strategy profile -> DB + LangGraph store

## 18. What Must Not Live Only in Prompt Text

These should always exist in executable config:

- risk thresholds
- preset values
- lane enablement defaults
- retry counts
- min trade amount
- scraper auth settings
- quote and price impact enforcement behavior
