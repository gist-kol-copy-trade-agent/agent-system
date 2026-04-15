# Local Stack Runbook

## 1. Prepare Env Files

From repo root:

```bash
cp system/.env.standalone.example system/.env
cp scraper/.env.example scraper/.env
```

Fill at least:

- `system/.env`
  - `OPENAI_API_KEY`
  - `APP_WEBHOOK_SECRET`
  - `TELEGRAM_BOT_TOKEN` if using Telegram polling
- `scraper/.env`
  - `SCRAPER_TELEGRAM_API_ID`
  - `SCRAPER_TELEGRAM_API_HASH`

## 1.1 Reproducible Local Dev Envs

Use separate virtualenvs for `system` and `scraper`.

Reason:

- both services expose a top-level Python package named `app`
- installing both into the same editable environment is easy to confuse during local development
- separate envs make test and runtime behavior more reproducible

Bootstrap:

```bash
make dev-venvs
```

Run tests:

```bash
make test-system
make test-scraper
```

## 2. Start Core Stack

```bash
docker compose up -d postgres scraper app-http
```

This gives:

- bot HTTP app on `http://localhost:8000`
- scraper API on `http://localhost:8010`
- Postgres on `localhost:5432`

Inside the compose network:

- bot calls scraper at `http://scraper:8010`
- scraper posts webhooks back to bot at `http://app-http:8000/webhooks/scraper/messages`

## 3. Optional Workers

Telegram polling bot:

```bash
docker compose --profile telegram up -d app-telegram
```

Exit monitor:

```bash
docker compose --profile monitor up -d app-exit-monitor
```

## 4. Logs

```bash
docker compose logs -f app-http
docker compose logs -f scraper
docker compose logs -f app-telegram
docker compose logs -f app-exit-monitor
```

## 5. Health Checks

Bot:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/readiness
```

Scraper:

```bash
curl http://localhost:8010/healthz
curl http://localhost:8010/readiness

Interpretation:

- `system /readiness` now distinguishes base runtime checks from execution-critical readiness.
- pay attention to `checks.trading_runtime_ready.ok` before treating the bot as eligible for supervised real-money operation.
- `trading_runtime_ready` requires:
  - DB reachable
  - checkpointer backend available
  - `onchainos` binary present and a read-only probe succeeds
  - OpenAI key configured
  - scraper reachable
  - Telegram client configured
  - at least one usable logged-in wallet session

Preflight command:

```bash
make preflight-system
```

Behavior:

- prints readiness JSON
- exits `0` only when `trading_runtime_ready=true`
- exits `2` when the stack is up but not ready for supervised trading operation
```

## 6. Notes

- Root `docker-compose.yml` is the primary local orchestration file.
- `system/docker-compose.standalone.yml` can still be used if you want to run only the bot service stack without the scraper service.
- The scraper is MVP-only:
  - live message ingestion uses polling, not a scalable worker fleet,
  - historical fetch jobs run in-process,
  - retry behavior is minimal and not yet a dedicated retry queue.

## 7. Bot-Only Standalone Mode

If you want to run only the bot service stack from `system/`:

```bash
cp system/.env.standalone.example system/.env
cd system
docker compose -f docker-compose.standalone.yml up -d postgres app-http
docker compose -f docker-compose.standalone.yml --profile telegram up -d app-telegram
docker compose -f docker-compose.standalone.yml --profile monitor up -d app-exit-monitor
```

In this mode:

- if `OKX_AGENT_SCRAPER__BASE_URL` is unset, the bot uses `NoopScraperClient`
- if `OKX_AGENT_SCRAPER__BASE_URL` is set, the standalone bot can still call an external scraper service
