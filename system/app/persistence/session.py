from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.persistence.base import Base


@lru_cache(maxsize=1)
def build_engine():
    settings = get_settings()
    return create_engine(settings.persistence.database_url, future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def build_session_factory():
    engine = build_engine()
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)


def create_all() -> None:
    engine = build_engine()
    Base.metadata.create_all(engine)
