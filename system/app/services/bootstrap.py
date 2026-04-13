from app.config.settings import get_settings
from app.observability.logging import configure_logging
from app.persistence.session import create_all


def bootstrap_application() -> None:
    settings = get_settings()
    configure_logging(settings.environment)
    create_all()
