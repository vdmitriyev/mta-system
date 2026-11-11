"""SQLite database of the app (users, exercises, reviews, bonus points, settings)."""

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    def to_dict(self) -> dict:
        return {
            column.name: getattr(self, column.name) for column in self.__table__.columns
        }


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
_engine = None


def init_engine(database_url: str):
    """Creates the engine and binds the sessions to it"""

    global _engine
    if _engine is not None:
        _engine.dispose()

    db_file = make_url(database_url).database
    if db_file and db_file != ":memory:":
        os.makedirs(os.path.dirname(db_file), exist_ok=True)

    # Requests and background tasks run in threads: each one uses its own session
    _engine = create_engine(
        database_url, connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _record):
        # WAL: readers do not block the writer (several workers use one file)
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine():
    return _engine


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Database session for code outside of a request (background tasks, CLI)"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
