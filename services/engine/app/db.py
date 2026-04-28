"""SQLite engine + session factory.

The engine service is the only writer. WAL mode + a generous busy_timeout
keeps reads non-blocking under contention.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_engine(db_path: str | Path) -> Engine:
    """Open (or create) the SQLite engine and apply WAL PRAGMAs."""
    global _engine, _SessionLocal

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"sqlite:///{db_path}"
    _engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 5.0},
        future=True,
    )

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("init_engine() not called")
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session and closes it after the request."""
    if _SessionLocal is None:
        raise RuntimeError("init_engine() not called")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def session_scope() -> Session:
    """Open a session for use outside FastAPI request scope (engine-internal)."""
    if _SessionLocal is None:
        raise RuntimeError("init_engine() not called")
    return _SessionLocal()
