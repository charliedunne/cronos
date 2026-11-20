"""Database engine, session factory, and declarative base."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def _build_engine():
    """Create the SQLAlchemy engine from application settings.

    @return A configured SQLAlchemy engine.
    """
    return create_engine(get_settings().database_url)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
