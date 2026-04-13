# RUNBOOK (MVP v1)

## 1. Prepare Environment

1. Copy env template:

```bash
cp .env.example .env
```

2. Fill required values in `.env`:
- `OPENAI_API_KEY`
- `APP_WEBHOOK_SECRET`
- `APP_CALLBACK_URL_MESSAGES` (public URL scraper can call)
- `TELEGRAM_BOT_TOKEN` (if running polling bot)

## 2. Run with Docker Compose

From `system/`:

1. Start HTTP app + Postgres:

```bash
docker compose up -d postgres app-http
```

2. Optional: start Telegram polling worker:

```bash
docker compose --profile telegram up -d app-telegram
```

3. Optional: start exit monitor worker (cron-like loop for position exit checks):

```bash
docker compose --profile monitor up -d app-exit-monitor
```

4. Check logs:

```bash
docker compose logs -f app-http
docker compose logs -f app-telegram
docker compose logs -f app-exit-monitor
```

## 3. Local (non-Docker) Run

From `system/`:

1. Install deps:

```bash
pip install -e .
```

2. Ensure Postgres is available and set:

```bash
export OKX_AGENT_PERSISTENCE__DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/okx_agent
```

3. Run HTTP server:

```bash
python -m app.workers.http_server
```

4. Run Telegram polling bot (another terminal):

```bash
python -m app.workers.telegram_polling
```

5. Run exit monitor loop (another terminal):

```bash
python -m app.workers.exit_monitor
```

## 4. Endpoints

- `GET /healthz`
- `GET /readiness`
- `POST /webhooks/scraper/messages`
- `POST /webhooks/scraper/follow-profile`

Webhook auth headers:
- `x-scraper-timestamp`
- `x-scraper-signature`

## 5. Ops Notes

- This repo currently wires `NoopScraperClient` by default in runtime, so scraper register/unregister is scaffold behavior unless a real scraper adapter is injected.
- `/status` is wallet-only by contract.
- `/history` now queries multi-chain deterministically based on DB closed positions + deterministic `begin/end` window.
- Exit loop interval is controlled by `OKX_AGENT_MONITORING__POSITION_REFRESH_INTERVAL_SECONDS`.
