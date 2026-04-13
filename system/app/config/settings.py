from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseModel):
    parsing_model: str = "openai:gpt-5-mini"
    decision_model: str = "openai:gpt-5"
    exit_model: str = "openai:gpt-5-mini"
    summary_model: str = "openai:gpt-5-mini"
    timeout_seconds: int = 30
    max_retries: int = 2


class LangGraphSettings(BaseModel):
    checkpointer_backend: Literal["memory", "postgres"] = "memory"
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


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OKX_AGENT_", env_nested_delimiter="__", case_sensitive=False)

    environment: Literal["development", "staging", "production"] = "development"
    timezone: str = "Asia/Ho_Chi_Minh"
    models: ModelSettings = Field(default_factory=ModelSettings)
    langgraph: LangGraphSettings = Field(default_factory=LangGraphSettings)
    wallet: WalletSettings = Field(default_factory=WalletSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
