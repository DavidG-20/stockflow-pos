"""SQLAlchemy engine, session factory, and declarative base."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from stockflow_pos.core.config import settings


def _build_engine(database_url: str):
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    return create_engine(database_url, connect_args=connect_args)


engine = _build_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all ORM entities."""


def get_db() -> Generator[Session, None, None]:
    """Yield a scoped database session per FastAPI request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
