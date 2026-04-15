from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.persistence.repositories import ChannelSubscriptionRepository, DeliveryAttemptRepository, HistoricalFetchJobRepository
from app.persistence.session import build_session_factory, create_all
from app.schemas import (
    FetchChannelMessagesRequest,
    FetchChannelMessagesResponse,
    RegisterChannelRequest,
    RegisterChannelResponse,
    UnregisterChannelRequest,
    UnregisterChannelResponse,
)
from app.services.runtime import ScraperRuntime
from app.services.subscription_service import SubscriptionService
from app.services.telethon_gateway import TelethonPublicChannelGateway
from app.services.webhook_delivery import WebhookDeliveryService


def create_app(
    *,
    telegram_gateway=None,
) -> FastAPI:
    create_all()
    session_factory = build_session_factory()
    subscription_repository = ChannelSubscriptionRepository(session_factory)
    history_repository = HistoricalFetchJobRepository(session_factory)
    delivery_repository = DeliveryAttemptRepository(session_factory)
    gateway = telegram_gateway or TelethonPublicChannelGateway()
    subscription_service = SubscriptionService(
        subscription_repository=subscription_repository,
        history_repository=history_repository,
        telegram_gateway=gateway,
    )
    runtime = ScraperRuntime(
        subscription_repository=subscription_repository,
        history_repository=history_repository,
        telegram_gateway=gateway,
        delivery_service=WebhookDeliveryService(delivery_repository),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await runtime.start()
        yield
        await runtime.stop()

    app = FastAPI(title="OKX Telegram Scraper", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.get("/readiness")
    async def readiness() -> dict:
        database_ok = False
        database_detail = "unknown"
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1"))
            database_ok = True
            database_detail = "ok"
        except Exception as exc:  # pragma: no cover - integration path
            database_detail = str(exc)

        gateway_ok = False
        gateway_detail = "gateway readiness check unavailable"
        if hasattr(gateway, "check_readiness"):
            gateway_ok, gateway_detail = await gateway.check_readiness()  # type: ignore[attr-defined]

        runtime_loops = {
            "running": runtime._running,
            "task_count": len(runtime._tasks),
            "tasks_alive": all(not task.done() for task in runtime._tasks) if runtime._tasks else False,
        }
        checks = {
            "database": {"ok": database_ok, "detail": database_detail},
            "telegram_gateway": {"ok": gateway_ok, "detail": gateway_detail},
            "runtime_loops": {"ok": bool(runtime_loops["running"] and runtime_loops["tasks_alive"]), "detail": str(runtime_loops)},
        }
        return {"ok": all(item["ok"] for item in checks.values()), "checks": checks}

    @app.post("/register/channel_name", response_model=RegisterChannelResponse)
    async def register_channel(request: RegisterChannelRequest) -> RegisterChannelResponse:
        return await subscription_service.register_channel(request)

    @app.post("/unregister/channel_name", response_model=UnregisterChannelResponse)
    async def unregister_channel(request: UnregisterChannelRequest) -> UnregisterChannelResponse:
        return subscription_service.unregister_channel(request)

    @app.post("/fetch/channel_name/messages", response_model=FetchChannelMessagesResponse)
    async def fetch_channel_messages(request: FetchChannelMessagesRequest) -> FetchChannelMessagesResponse:
        await subscription_service.create_historical_fetch_job(request)
        return FetchChannelMessagesResponse(
            ok=True,
            request_id=request.request_id,
            status="accepted",
            delivery_mode=request.delivery_mode,
        )

    return app
