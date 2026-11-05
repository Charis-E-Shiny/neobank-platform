"""Database engine and session management (SQLAlchemy 2.x)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC timestamp. All timestamps in the database are UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)

    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        # One shared connection so an in-memory database survives across sessions (tests).
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class Database:
    def __init__(self, url: str, *, create_tables: bool = True) -> None:
        from . import models  # noqa: F401  (registers tables on Base.metadata)

        self.engine = _make_engine(url)
        self._sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        if create_tables:
            # Convenient for development and SQLite. In production, apply sql/schema.sql
            # (or Alembic migrations) instead and set create_tables=False.
            Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self._sessions()
