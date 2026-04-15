from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.persistence.base import Base


@lru_cache(maxsize=1)
def build_engine():
    return create_engine(get_settings().scraper_database_url, future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def build_session_factory():
    return sessionmaker(bind=build_engine(), class_=Session, expire_on_commit=False, future=True)


def create_all() -> None:
    Base.metadata.create_all(build_engine())
