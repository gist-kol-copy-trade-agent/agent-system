# Scraper Service

Telegram scraper service for the OKX agent architecture.

Responsibilities:

- register/unregister public channels,
- fetch historical messages for `/follow` profiling,
- poll latest public channel messages,
- deliver signed webhook payloads back to the main bot service.

Runtime shape:

- FastAPI HTTP server,
- SQLite by default,
- SQLite persisted in Docker at `/app/data/scraper.db`,
- background loops for live polling and historical fetch jobs,
- Telethon gateway for Telegram reads.

Quick start:

```bash
cd scraper
pip install -e .[dev]
cp .env.example .env
python -m app.workers.http_server
```

Recommended local test setup from repo root:

```bash
make scraper-venv
make test-scraper
```

Using a dedicated scraper virtualenv is preferred because the repo also contains `system/`, which exports its own top-level `app` package.

Full local stack:

```bash
cd ..
docker compose up -d postgres scraper app-http
```

Docker:

```bash
cd scraper
docker build -t okx-telegram-scraper .
docker run --rm -p 8010:8010 --env-file .env okx-telegram-scraper
```

Main endpoints:

- `POST /register/channel_name`
- `POST /unregister/channel_name`
- `POST /fetch/channel_name/messages`
- `GET /healthz`
- `GET /readiness`
