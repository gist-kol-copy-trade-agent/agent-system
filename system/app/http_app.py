from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.webhook import ScraperFollowProfileWebhookPayload, ScraperWebhookPayload
from app.services.app_runtime import ApplicationRuntime
from app.services.webhook_intake import WebhookAuthError


@dataclass(frozen=True)
class WebhookHTTPResult:
    status_code: int
    body: dict[str, Any]


class ScraperWebhookHandler:
    def __init__(self, runtime: ApplicationRuntime, *, webhook_secret: str) -> None:
        self.runtime = runtime
        self.webhook_secret = webhook_secret

    def handle(self, *, body: bytes, timestamp: str, signature: str) -> WebhookHTTPResult:
        try:
            self.runtime.webhook_intake.verify_signature(
                body=body,
                timestamp=timestamp,
                secret=self.webhook_secret,
                provided_signature=signature,
            )
        except WebhookAuthError:
            return WebhookHTTPResult(status_code=401, body={"ok": False, "error": "invalid_signature"})

        payload = ScraperWebhookPayload.model_validate_json(body)
        accepted = self.runtime.webhook_intake.accept_event(payload)
        if accepted is None:
            return WebhookHTTPResult(status_code=200, body={"ok": True, "deduplicated": True})

        workflow = self.runtime.signal_queue.enqueue_signal(accepted)
        return WebhookHTTPResult(
            status_code=202,
            body={
                "ok": True,
                "thread_id": workflow.thread_id,
                "workflow_type": workflow.workflow_type,
                "status": "accepted",
            },
        )


class ScraperFollowProfileWebhookHandler:
    def __init__(self, runtime: ApplicationRuntime, *, webhook_secret: str) -> None:
        self.runtime = runtime
        self.webhook_secret = webhook_secret

    def handle(self, *, body: bytes, timestamp: str, signature: str) -> WebhookHTTPResult:
        try:
            self.runtime.webhook_intake.verify_signature(
                body=body,
                timestamp=timestamp,
                secret=self.webhook_secret,
                provided_signature=signature,
            )
        except WebhookAuthError:
            return WebhookHTTPResult(status_code=401, body={"ok": False, "error": "invalid_signature"})

        payload = ScraperFollowProfileWebhookPayload.model_validate_json(body)
        accepted = self.runtime.follow_command_service.accept_profile_callback(payload)
        return WebhookHTTPResult(
            status_code=202,
            body={
                "ok": True,
                "source_id": accepted.source_id,
                "channel_name": accepted.channel_name,
                "suggested_conviction": accepted.suggested_conviction,
                "status": accepted.status,
            },
        )


def create_http_app(runtime: ApplicationRuntime, *, webhook_secret: str):
    try:
        from fastapi import BackgroundTasks, FastAPI, Header, Request
        from fastapi.responses import JSONResponse
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("FastAPI is not installed.") from exc

    handler = ScraperWebhookHandler(runtime, webhook_secret=webhook_secret)
    follow_profile_handler = ScraperFollowProfileWebhookHandler(runtime, webhook_secret=webhook_secret)
    app = FastAPI(title="OKX Agent System", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/readiness")
    async def readiness() -> dict[str, Any]:
        result = runtime.readiness.run()
        return {"ok": result.ok, "checks": result.checks}

    @app.post("/webhooks/scraper/messages")
    async def scraper_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        x_scraper_timestamp: str = Header(...),
        x_scraper_signature: str = Header(...),
    ):
        body = await request.body()
        result = handler.handle(body=body, timestamp=x_scraper_timestamp, signature=x_scraper_signature)
        if result.status_code == 202 and result.body.get("ok") and result.body.get("deduplicated") is not True:
            thread_id = result.body.get("thread_id")
            workflow_type = result.body.get("workflow_type")
            if thread_id and workflow_type:
                from app.services.workflow_runtime import EnqueuedWorkflow

                payload = ScraperWebhookPayload.model_validate_json(body)
                background_tasks.add_task(
                    runtime.signal_runtime.invoke,
                    EnqueuedWorkflow(thread_id=thread_id, workflow_type=workflow_type, payload=payload),
                )
        return JSONResponse(status_code=result.status_code, content=result.body)

    @app.post("/webhooks/scraper/follow-profile")
    async def scraper_follow_profile_webhook(
        request: Request,
        x_scraper_timestamp: str = Header(...),
        x_scraper_signature: str = Header(...),
    ):
        body = await request.body()
        result = follow_profile_handler.handle(body=body, timestamp=x_scraper_timestamp, signature=x_scraper_signature)
        return JSONResponse(status_code=result.status_code, content=result.body)

    return app
