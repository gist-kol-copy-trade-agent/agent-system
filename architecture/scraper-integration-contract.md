# Scraper Integration Contract

## 1. Purpose

This document defines the integration contract between:

- the trading bot service
- the Telegram scraper service

The integration has two directions:

- outbound bot -> scraper API calls
- inbound scraper -> bot webhook delivery

For `/follow`, there is also a pre-registration profiling path:

- outbound bot -> scraper historical fetch request
- optional async scraper -> bot profiling webhook callback

## 2. Integration Responsibilities

## 2.1 Bot Responsibilities

The bot is responsible for:

- registering followed channels with the scraper,
- unregistering stopped channels from the scraper,
- receiving scraped Telegram messages via webhook,
- validating, deduplicating, and persisting inbound webhook events,
- returning deterministic webhook acknowledgements.

## 2.2 Scraper Responsibilities

The scraper is responsible for:

- accepting channel registration requests,
- tracking subscribed channels,
- scraping new Telegram messages from those channels,
- delivering normalized webhook events to the bot,
- retrying delivery on transient failures.

## 3. Outbound API: Register Channel

## Endpoint

```text
POST /register/channel_name
```

This is the bot -> scraper call.

## Purpose

Register a Telegram source for active scraping.

## Request Body

```json
{
  "source_id": "src_123",
  "channel_name": "some_kol_channel",
  "channel_url": "https://t.me/some_kol_channel",
  "callback_url": "https://bot.example.com/webhooks/scraper/messages",
  "callback_secret": "bot-managed-shared-secret",
  "user_id": "user_123",
  "bot_id": "bot_main",
  "enabled": true
}
```

## Required Fields

- `source_id`
- `channel_name`
- `callback_url`
- `callback_secret`
- `user_id`

## Response

```json
{
  "ok": true,
  "scraper_subscription_id": "sub_456",
  "channel_name": "some_kol_channel",
  "status": "registered"
}
```

## Behavior Rules

- registration should be idempotent for the same `source_id`
- if the channel is already registered, scraper should return a successful normalized response
- scraper should persist `scraper_subscription_id`

## Failure Cases

Example:

```json
{
  "ok": false,
  "error_code": "CHANNEL_NOT_FOUND",
  "message": "Channel could not be resolved"
}
```

The bot should:

- not mark the source fully active until registration succeeds
- store the failure reason
- return an actionable Telegram message to the user

## 4. Outbound API: Unregister Channel

## Endpoint

```text
POST /unregister/channel_name
```

This is the bot -> scraper call.

## Purpose

Stop scraping a previously registered Telegram source.

## Request Body

```json
{
  "source_id": "src_123",
  "channel_name": "some_kol_channel",
  "scraper_subscription_id": "sub_456",
  "user_id": "user_123"
}
```

## Response

```json
{
  "ok": true,
  "status": "unregistered",
  "source_id": "src_123"
}
```

## Behavior Rules

- unregister should be idempotent
- if the scraper no longer has the subscription, it should still return success
- bot should mark the source inactive locally even if scraper reports it was already absent

## 4B. Outbound API: Fetch Historical Channel Messages

## Endpoint

```text
POST /fetch/channel_name/messages
```

This is the bot -> scraper call.

## Purpose

Fetch recent channel messages for cold-start profiling before the bot asks the user to confirm follow.

This endpoint is intended for `/follow` pre-registration analysis.

## Request Body

```json
{
  "request_id": "follow_profile_req_123",
  "source_id": "src_123",
  "channel_name": "some_kol_channel",
  "channel_url": "https://t.me/some_kol_channel",
  "lookback_days": 7,
  "limit": 500,
  "delivery_mode": "async_webhook",
  "callback_url": "https://bot.example.com/webhooks/scraper/follow-profile",
  "callback_secret": "bot-managed-shared-secret",
  "user_id": "user_123"
}
```

## Required Fields

- `request_id`
- `source_id`
- `channel_name`
- `lookback_days`
- `delivery_mode`
- `callback_url`
- `callback_secret`
- `user_id`

## Behavior Rules

- scraper should fetch messages for the requested lookback window, defaulting to the most recent 7 days for the MVP flow
- scraper may truncate to `limit` if the channel is very active
- scraper should not register the channel as an active live subscription in this step
- scraper should support at least `delivery_mode = async_webhook`
- this call may be long-running; the bot should not block the Telegram request waiting for completion

## Immediate Response

```json
{
  "ok": true,
  "request_id": "follow_profile_req_123",
  "status": "accepted",
  "delivery_mode": "async_webhook"
}
```

## Failure Cases

Example:

```json
{
  "ok": false,
  "error_code": "CHANNEL_FETCH_UNAVAILABLE",
  "message": "Historical fetch is temporarily unavailable"
}
```

The bot should:

- keep the source in local `profiling_pending` or `profiling_failed` state
- return an actionable Telegram message to the user
- avoid registering the channel for live follow until profiling completes and the user confirms

## 4C. Inbound Webhook: Historical Follow Profiling Result

## Endpoint

```text
POST /webhooks/scraper/follow-profile
```

This is the scraper -> bot callback for historical sample delivery.

## Purpose

Deliver the requested historical messages so the bot can run:

- LLM-based call extraction
- market-history-based retrospective evaluation
- channel conviction suggestion

## Request Headers

Required:

- `X-Scraper-Signature`
- `X-Scraper-Timestamp`
- `X-Request-Id`

## Request Body

```json
{
  "request_id": "follow_profile_req_123",
  "source_id": "src_123",
  "channel_name": "some_kol_channel",
  "lookback_days": 7,
  "message_count": 142,
  "messages": [
    {
      "message_id": "123",
      "message_text": "Buy ETH now, target 3.5k",
      "message_timestamp": "2026-04-13T09:15:00Z",
      "message_url": "https://t.me/some_kol_channel/123",
      "media_blobs": [
        {
          "kind": "image",
          "mime_type": "image/jpeg",
          "telegram_file_id": "123456789",
          "base64_data": "<base64-image-bytes>"
        }
      ]
    }
  ],
  "raw_payload": {
    "scraper": "optional vendor payload"
  }
}
```

## Required Fields

- `request_id`
- `source_id`
- `channel_name`
- `messages`

## Bot-Side Behavior

When this webhook is received, the bot should:

1. verify signature and freshness
2. validate payload schema
3. persist profiling request result and sampled messages
4. run call extraction with LLM
5. fetch post-call price history with `okx-dex-market` / `onchainos market kline`
6. compute retrospective 1-day hit-rate / win-rate style metrics
7. build a channel profiling summary
8. send the analysis to the user and ask whether they want to follow the channel

The webhook handler may enqueue a profiling workflow instead of doing the entire analysis inline.

Media note:

- for messages with Telegram images, scraper should send normalized `media_blobs`
- `message_url` alone is not enough because the bot must be able to pass image bytes directly into multimodal parsing / profiling
- MVP requires image blobs only for images; other media types may be omitted or passed only in raw payload

## Profiling Workflow Output Contract

The bot-side profiling result should produce, at minimum:

```json
{
  "source_id": "src_123",
  "channel_name": "some_kol_channel",
  "sample_window_days": 7,
  "sample_message_count": 142,
  "extracted_call_count": 19,
  "evaluated_call_count": 15,
  "win_rate_1d": 0.6,
  "median_return_1d_pct": 8.4,
  "major_asset_bias": 0.7,
  "regular_token_bias": 0.3,
  "suggested_conviction": "medium",
  "profiling_summary": "Channel shows solid 1-day follow-through on major-asset calls, with moderate consistency."
}
```

This result should be persisted before asking the user for final follow confirmation.

## 5. Inbound Webhook: New Telegram Message

## Endpoint

```text
POST /webhooks/scraper/messages
```

This is the scraper -> bot call.

## Purpose

Deliver newly scraped Telegram messages for followed channels.

## Request Headers

Required:

- `X-Scraper-Signature`
- `X-Scraper-Timestamp`
- `X-Event-Id`

Recommended:

- `Content-Type: application/json`

## Authentication

The bot should verify:

- signature generated from request body + timestamp using the shared secret
- timestamp freshness within a short replay window

If verification fails:

- return `401` or `403`
- do not persist the event

## Request Body

```json
{
  "event_id": "evt_789",
  "event_type": "telegram.message.new",
  "scraper_subscription_id": "sub_456",
  "source_id": "src_123",
  "channel_name": "some_kol_channel",
  "channel_url": "https://t.me/some_kol_channel",
  "message_id": "12345",
  "message_text": "Buy ETH now, target 3.5k",
  "message_timestamp": "2026-04-13T09:15:00Z",
  "message_url": "https://t.me/some_kol_channel/12345",
  "media_blobs": [
    {
      "kind": "image",
      "mime_type": "image/jpeg",
      "telegram_file_id": "123456789",
      "base64_data": "<base64-image-bytes>"
    }
  ],
  "raw_payload": {
    "telegram": "original scraper-specific payload"
  }
}
```

## Required Fields

- `event_id`
- `event_type`
- `source_id`
- `channel_name`
- `message_id`
- `message_text`
- `message_timestamp`

Recommended when media exists:

- `media_blobs`

## Response

On success:

```json
{
  "ok": true,
  "event_id": "evt_789",
  "status": "accepted"
}
```

On duplicate:

```json
{
  "ok": true,
  "event_id": "evt_789",
  "status": "duplicate_ignored"
}
```

## Bot-Side Behavior

When image blobs are present, the bot should:

- persist them inside the raw webhook payload
- pass them to the parsing agent as optional multimodal input
- treat image interpretation as supporting evidence, not as permission to invent missing token identifiers

When the webhook is received, the bot should:

1. verify signature and freshness
2. validate payload schema
3. enforce idempotency on `event_id`
4. persist raw event and normalized message record
5. enqueue the signal-intake workflow
6. return success quickly

The webhook handler should not perform full trade analysis inline before responding.

## 6. Event Idempotency

The bot should treat these as uniqueness keys:

- primary: `event_id`
- secondary safety key: `source_id + message_id + message_timestamp`

The scraper should also avoid sending duplicate events when possible.

## 7. `/follow` Integration Sequence

The intended `/follow` sequence for MVP is:

1. user sends `/follow <channel>`
2. bot validates and normalizes source input
3. bot persists local source in `profiling_pending`
4. bot calls `POST /fetch/channel_name/messages`
5. scraper asynchronously returns sampled messages via `POST /webhooks/scraper/follow-profile`
6. bot runs LLM call extraction
7. bot runs retrospective market evaluation with `okx-dex-market`
8. bot sends channel analysis to the user with a suggested conviction level
9. user confirms whether to actually follow the channel
10. only after confirmation, bot calls `POST /register/channel_name`
11. bot marks the source active locally

## 7. Retry Policy

The scraper should retry webhook delivery on:

- `408`
- `429`
- `5xx`

The scraper should not retry on:

- `2xx`
- `4xx` auth/schema failures except where explicitly configured

Recommended retry schedule:

- immediate retry after short backoff
- then exponential backoff
- max bounded attempts

## 8. Suggested HTTP Status Behavior

Bot webhook endpoint should return:

- `200` for accepted or duplicate-ignored events
- `400` for malformed payload
- `401` or `403` for signature/auth failure
- `409` only if business logic wants to signal a hard conflict
- `429` for rate-limit / overload
- `500` for transient internal failure

## 9. State Mutations

## 9.1 On Register

Bot should update:

- `followed_sources.status`
- `followed_sources.scraper_subscription_id`
- source registration audit log

## 9.2 On Unregister

Bot should update:

- `followed_sources.status`
- `followed_sources.unsubscribed_at`
- source deactivation audit log

## 9.3 On Webhook Receive

Bot should create:

- raw webhook event log
- source message record
- signal ingestion job / workflow run

## 10. Recommended Persistence Fields

For `followed_sources`:

- `source_id`
- `channel_name`
- `channel_url`
- `scraper_subscription_id`
- `status`
- `registered_at`
- `unsubscribed_at`

For raw webhook events:

- `event_id`
- `headers`
- `payload`
- `received_at`
- `verification_status`
- `processing_status`

## 11. Command Integration

### `/follow`

After local validation, the bot should:

1. create or upsert the source locally in a pending state
2. call `POST /register/channel_name`
3. persist registration result
4. return final source status to Telegram

### `/stop`

After resolving the source, the bot should:

1. call `POST /unregister/channel_name`
2. mark the source inactive locally
3. return final status to Telegram

## 12. Versioning Recommendation

If the integration is expected to evolve, use versioned paths such as:

```text
/api/v1/register/channel_name
/api/v1/unregister/channel_name
/api/v1/webhooks/scraper/messages
```

## 13. Minimal V1 Requirement

For v1, the integration can stay simple as long as it includes:

- a shared-secret signature check,
- event idempotency,
- fast webhook acknowledgement,
- deterministic register/unregister APIs,
- persisted mapping between local source and scraper subscription.
