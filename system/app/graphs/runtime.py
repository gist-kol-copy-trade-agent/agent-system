from functools import lru_cache
from typing import Any

try:
    from langgraph.checkpoint.memory import InMemorySaver
except ModuleNotFoundError:  # pragma: no cover - dependency fallback for scaffold validation
    class InMemorySaver:  # type: ignore[no-redef]
        """Fallback stub used when langgraph is not installed yet."""

        pass

from app.config.settings import AppSettings, get_settings


@lru_cache(maxsize=4)
def _build_cached_checkpointer(backend: str, database_url: str) -> Any:
    if backend == "memory":
        return InMemorySaver()

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ModuleNotFoundError as exc:  # pragma: no cover - optional integration
        raise RuntimeError(
            "LangGraph Postgres checkpointer backend was requested, but "
            "`langgraph-checkpoint-postgres` is not installed."
        ) from exc

    saver = PostgresSaver.from_conn_string(database_url)
    saver.setup()
    return saver


def build_checkpointer(settings: AppSettings | None = None) -> Any:
    resolved = settings or get_settings()
    return _build_cached_checkpointer(
        resolved.langgraph.checkpointer_backend,
        resolved.persistence.database_url,
    )


def build_thread_id(prefix: str, identifier: str) -> str:
    return f"{prefix}:{identifier}"


def invoke_graph(graph: Any, state: Any, *, config: dict[str, Any], durability: str | None = None) -> Any:
    if durability is None:
        return graph.invoke(state, config=config)
    try:
        return graph.invoke(state, config=config, durability=durability)
    except TypeError:
        return graph.invoke(state, config=config)
