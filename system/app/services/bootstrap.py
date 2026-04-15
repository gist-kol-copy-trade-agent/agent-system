from app.config.settings import get_settings
from app.observability.logging import configure_logging
from app.persistence.session import build_session_factory, create_all
from app.services.readiness import RuntimeReadinessService


def bootstrap_application() -> dict:
    settings = get_settings()
    configure_logging(settings.environment)
    create_all()
    readiness = RuntimeReadinessService(session_factory=build_session_factory()).run()
    return {"environment": settings.environment, "readiness": {"ok": readiness.ok, "checks": readiness.checks}}
