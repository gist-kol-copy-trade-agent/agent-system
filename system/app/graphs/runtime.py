from typing import Any

try:
    from langgraph.checkpoint.memory import InMemorySaver
except ModuleNotFoundError:  # pragma: no cover - dependency fallback for scaffold validation
    class InMemorySaver:  # type: ignore[no-redef]
        """Fallback stub used when langgraph is not installed yet."""

        pass

from app.config.settings import get_settings


def build_checkpointer() -> Any:
    settings = get_settings()
    if settings.langgraph.checkpointer_backend == "memory":
        return InMemorySaver()

    # Postgres-backed checkpointer can be added in a later phase.
    return InMemorySaver()


def build_thread_id(prefix: str, identifier: str) -> str:
    return f"{prefix}:{identifier}"
