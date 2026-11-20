"""SQLite database of the app (users, exercises, reviews, bonus points, settings)."""

import os
import re
import sqlite3
import tarfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
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


def backup_sqlite(db_file: Path, backup_dir: Path) -> Path:
    """Copies the SQLite database to <backup_dir>/<YYYYmmdd-HHMMSS>-<file name>.

    Uses the backup API of SQLite: the copy is complete also while the app writes.
    """

    if not db_file.is_file():
        raise FileNotFoundError(f"No database at {db_file}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{stamp}-{db_file.name}"
    source = sqlite3.connect(db_file)
    copy = sqlite3.connect(target)
    try:
        with copy:
            source.backup(copy)
    finally:
        copy.close()
        source.close()
    return target


def prune_backups(backup_dir: Path, name: str, keep: int) -> list:
    """Deletes the oldest <YYYYmmdd-HHMMSS>-<name> files, so that keep files stay.

    keep 0: nothing is deleted. Returns the deleted files.
    """

    if keep <= 0 or not backup_dir.is_dir():
        return []
    pattern = re.compile(r"^\d{8}-\d{6}-" + re.escape(name) + "$")
    files = sorted(
        (path for path in backup_dir.iterdir() if pattern.match(path.name)),
        key=lambda path: path.name,
        reverse=True,
    )
    removed = files[keep:]
    for path in removed:
        path.unlink()
    return removed


def pack_folder(folder: Path, backup_dir: Path, name: str) -> Path | None:
    """Writes the folder to <backup_dir>/<YYYYmmdd-HHMMSS>-<name>.tar.gz.

    None: the folder does not exist.
    """

    if not folder.is_dir():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{stamp}-{name}.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        archive.add(folder, arcname=name)
    return target
