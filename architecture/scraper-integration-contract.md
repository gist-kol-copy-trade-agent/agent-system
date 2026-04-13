# Scraper Integration Contract

## 1. Purpose

This document defines the integration contract between:

- the trading bot service
- the Telegram scraper service

The integration has two directions:

- outbound bot -> scraper API calls
- inbound scraper -> bot webhook delivery

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

## 13. Minimal PoC Requirement

For the PoC, the integration can stay simple as long as it includes:

- a shared-secret signature check,
- event idempotency,
- fast webhook acknowledgement,
- deterministic register/unregister APIs,
- persisted mapping between local source and scraper subscription.
