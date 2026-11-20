"""Files that the admin offers for download, e.g. the tasks of the bonus exercises"""

import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import DOWNLOAD_MAX_MB, get_settings
from app.models import Downloads, Exercises
from app.submissions import (
    MB,
    SubmissionError,
    Upload,
)
from app.submissions import check_content as check_text_or_pdf
from app.submissions import split_filename, store_upload, unique_name
from app.web import send_file

logger = logging.getLogger(__name__)

# extension -> media type of the download
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".sql": "application/sql; charset=utf-8",
}
ALLOWED_TEXT = "PDF, ZIP, MD, TXT or SQL"


class DownloadError(Exception):
    """The file cannot be saved. The message is for the admin."""


@dataclass
class StoredFile:
    original_name: str
    stored_name: str
    size_bytes: int
    sha256: str
    content_type: str


def max_bytes() -> int:
    return DOWNLOAD_MAX_MB * MB


def root_dir() -> Path:
    return get_settings().downloads_dir


def file_path(item: Downloads) -> Path:
    """Path of the file. It must stay in DOWNLOADS_DIR."""

    root = root_dir().resolve()
    path = (root / item.stored_name).resolve()
    if not path.is_relative_to(root):
        raise DownloadError("The file is not in the downloads folder.")
    return path


def file_response(item: Downloads) -> FileResponse:
    """The file as a download; 404 if it is missing"""

    try:
        path = file_path(item)
    except DownloadError:
        path = None
    return send_file(path, item.content_type, item.original_name)


def check_content(ext: str, path: Path) -> bool:
    """Does the content fit the extension?"""

    if ext == ".zip":
        if not zipfile.is_zipfile(path):
            return False
        try:
            with zipfile.ZipFile(path):
                return True
        except zipfile.BadZipFile:
            return False
    if ext == ".sql":
        return check_text_or_pdf(".txt", path)
    return check_text_or_pdf(ext, path)


def store_file(upload: Upload) -> StoredFile:
    """Checks the file and saves it in DOWNLOADS_DIR"""

    stem, ext = split_filename(upload.filename)
    if not upload.filename:
        raise DownloadError("Choose a file.")
    if ext not in ALLOWED_TYPES:
        raise DownloadError(f"{upload.filename}: only {ALLOWED_TEXT} files.")
    folder = root_dir()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        temp_path, size, sha256 = store_upload(folder, upload, ext, max_bytes())
    except SubmissionError as error:
        raise DownloadError(
            f"{upload.filename}: the file is larger than {DOWNLOAD_MAX_MB} MB."
        ) from error
    try:
        if size == 0:
            raise DownloadError(f"{upload.filename}: the file is empty.")
        if not check_content(ext, temp_path):
            raise DownloadError(
                f"{upload.filename}: the content is not a {ext[1:].upper()} file."
            )
        stored_name = unique_name(folder, stem, ext)
        temp_path.rename(folder / stored_name)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    original = re.split(r"[\\/]", upload.filename)[-1][:255]
    return StoredFile(original, stored_name, size, sha256, ALLOWED_TYPES[ext])


def remove_file(stored_name: str) -> None:
    path = (root_dir() / stored_name).resolve()
    if path.is_relative_to(root_dir().resolve()):
        path.unlink(missing_ok=True)


def list_downloads(db: Session, only_visible: bool = False) -> list:
    query = db.query(Downloads)
    if only_visible:
        query = query.filter(Downloads.visible.is_(True))
    return query.order_by(Downloads.sort_order.asc(), Downloads.itid.asc()).all()


def get_download(db: Session, item_id: int) -> Downloads | None:
    return db.get(Downloads, item_id)


def bonus_exercises(db: Session) -> list:
    """Exercises with a bonus part: a download can belong to one of them"""

    return (
        db.query(Exercises)
        .filter(Exercises.has_bonus.is_(True))
        .order_by(Exercises.exercise_order.asc(), Exercises.code.asc())
        .all()
    )


def add_download(
    db: Session,
    stored: StoredFile,
    title: str,
    description: str,
    exercise_id: int | None,
    visible: bool,
) -> Downloads:
    items = list_downloads(db)
    item = Downloads(
        title=title or stored.original_name,
        description=description or None,
        exercise_id=exercise_id,
        visible=visible,
        sort_order=(items[-1].sort_order + 1) if items else 1,
        **stored.__dict__,
    )
    db.add(item)
    db.commit()
    return item


def replace_file(db: Session, item: Downloads, stored: StoredFile) -> None:
    old_name = item.stored_name
    for key, value in stored.__dict__.items():
        setattr(item, key, value)
    db.commit()
    remove_file(old_name)


def move(db: Session, item: Downloads, step: int) -> bool:
    """Moves the download one place up (-1) or down (+1). False: not possible."""

    items = list_downloads(db)
    index = items.index(item)
    other = index + step
    if other < 0 or other >= len(items):
        return False
    items[index], items[other] = items[other], items[index]
    for number, entry in enumerate(items, start=1):
        entry.sort_order = number
    db.commit()
    return True


def delete_download(db: Session, item: Downloads) -> None:
    stored_name = item.stored_name
    db.delete(item)
    db.commit()
    remove_file(stored_name)


def user_downloads(db: Session) -> list:
    """The visible downloads with their exercise"""

    exercises = {exercise.itid: exercise for exercise in bonus_exercises(db)}
    return [
        {"item": item, "exercise": exercises.get(item.exercise_id)}
        for item in list_downloads(db, only_visible=True)
    ]
