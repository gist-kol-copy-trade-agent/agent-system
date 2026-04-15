from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)

    scraper_host: str = "0.0.0.0"
    scraper_port: int = 8010
    scraper_database_url: str = "sqlite+pysqlite:///./scraper.db"
    scraper_poll_interval_seconds: int = 20
    scraper_history_fetch_batch_size: int = 5
    scraper_live_fetch_limit: int = 20
    scraper_webhook_timeout_seconds: int = 15
    scraper_signature_ttl_seconds: int = 300
    scraper_telegram_api_id: int | None = None
    scraper_telegram_api_hash: str | None = None
    scraper_telegram_session_name: str = "scraper_mvp"
    scraper_media_blob_max_bytes: int = 1048576
    scraper_media_blob_max_images_per_message: int = 2


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
