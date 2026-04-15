from functools import lru_cache
from typing import Literal
import os

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseModel):
    parsing_model: str = "openai:gpt-5.3"
    enrichment_model: str = "openai:gpt-5.4"
    decision_model: str = "openai:gpt-5.4"
    exit_model: str = "openai:gpt-5.4"
    swap_execution_model: str = "openai:gpt-5.4"
    follow_profiling_model: str = "openai:gpt-5.4"
    wallet_model: str = "openai:gpt-5.3-mini"
    position_tracker_model: str = "openai:gpt-5.3-mini"
    history_model: str = "openai:gpt-5.3-mini"
    trade_style_model: str = "openai:gpt-5.3-mini"
    summary_model: str = "openai:gpt-5.3-mini"
    timeout_seconds: int = 30
    max_retries: int = 2


class OpenAISettings(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    organization: str | None = None
    project: str | None = None


class LangGraphSettings(BaseModel):
    checkpointer_backend: Literal["memory", "postgres"] = "postgres"
    signal_durability: Literal["exit", "async", "sync"] = "sync"
    exit_durability: Literal["exit", "async", "sync"] = "sync"
    command_durability: Literal["exit", "async", "sync"] = "async"
    thread_prefix_signal: str = "signal"
    thread_prefix_position: str = "position"
    thread_prefix_command: str = "command"
    resume_on_restart: bool = True


class WalletSettings(BaseModel):
    major_execution_chain: str = "xlayer"
    major_assets: list[str] = Field(default_factory=lambda: ["BTC", "ETH", "SOL"])
    allow_cross_chain_funding: bool = False


class PersistenceSettings(BaseModel):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/okx_agent"


class MonitoringSettings(BaseModel):
    position_refresh_interval_seconds: int = 60
    cron_exit_evaluation_enabled: bool = True


class ScraperSettings(BaseModel):
    base_url: str | None = None
    timeout_seconds: int = 15


class NotificationSettings(BaseModel):
    mode: Literal["compact", "standard", "demo_longform"] = "standard"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OKX_AGENT_", env_nested_delimiter="__", case_sensitive=False)

    environment: Literal["development", "staging", "production"] = "development"
    timezone: str = "Asia/Ho_Chi_Minh"
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    langgraph: LangGraphSettings = Field(default_factory=LangGraphSettings)
    wallet: WalletSettings = Field(default_factory=WalletSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def ensure_openai_runtime_env(settings: AppSettings | None = None) -> None:
    resolved = settings or get_settings()
    api_key = resolved.openai.api_key or os.getenv("OPENAI_API_KEY")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    if resolved.openai.base_url:
        os.environ["OPENAI_BASE_URL"] = resolved.openai.base_url
    if resolved.openai.organization:
        os.environ["OPENAI_ORG_ID"] = resolved.openai.organization
    if resolved.openai.project:
        os.environ["OPENAI_PROJECT_ID"] = resolved.openai.project
