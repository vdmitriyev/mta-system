"""Files that the users submit for the exercises (reports).

The files are in SUBMISSIONS_DIR: <user-id>_<name>/<EXERCISE_CODE>/<file>.
Users can upload and delete them until the deadline (or their extension).
"""

import hashlib
import logging
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.emails import send_email
from app.models import Exercises, ExerciseSubmissions, SubmissionExtensions, Users

logger = logging.getLogger(__name__)

MB = 1024 * 1024
CHUNK_SIZE = 256 * 1024
MAX_NAME_LENGTH = 100
# extension -> media type of the download
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_TEXT = "PDF, TXT, MD or DOCX"


class SubmissionError(Exception):
    """The upload or delete is not possible. The message is for the user."""


@dataclass
class Upload:
    """A file of the upload form: name and an open binary file"""

    filename: str
    file: object


def max_bytes() -> int:
    return get_settings().submission_max_file_mb * MB


def root_dir() -> Path:
    return get_settings().submissions_dir


# ---- exercises and deadlines ----


def submission_exercises(db: Session, only_visible: bool = True) -> list:
    """The exercises with a submission part, ordered by exercise_order"""

    query = db.query(Exercises).filter(Exercises.has_submission.is_(True))
    if only_visible:
        query = query.filter(Exercises.visible.is_(True))
    return query.order_by(Exercises.exercise_order.asc(), Exercises.code.asc()).all()


def get_extension(
    db: Session, exercise_id: int, user_id: int
) -> SubmissionExtensions | None:
    return (
        db.query(SubmissionExtensions)
        .filter_by(exercise_id=exercise_id, user_id=user_id)
        .first()
    )


def effective_deadline(db: Session, exercise: Exercises, user_id: int):
    """The extension of the user, else the deadline of the exercise (None: no deadline)"""

    extension = get_extension(db, exercise.itid, user_id)
    return extension.deadline if extension else exercise.submission_deadline


def is_open(deadline: datetime | None, now: datetime | None = None) -> bool:
    """Deadlines are local times of the server (TZ), as the admin enters them"""

    return deadline is None or (now or datetime.now()) <= deadline


def set_extension(
    db: Session, exercise: Exercises, user_id: int, deadline: datetime, note: str
) -> None:
    extension = get_extension(db, exercise.itid, user_id)
    if extension is None:
        extension = SubmissionExtensions(exercise_id=exercise.itid, user_id=user_id)
        db.add(extension)
    extension.deadline = deadline
    extension.note = note.strip()[:200] or None
    db.commit()


def remove_extension(db: Session, exercise: Exercises, user_id: int) -> bool:
    extension = get_extension(db, exercise.itid, user_id)
    if extension is None:
        return False
    db.delete(extension)
    db.commit()
    return True


# ---- names of folders and files ----


def safe_part(text: str) -> str:
    """Only letters, digits, ".", "_" and "-"; no leading dots"""

    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text or "")
    return text.strip("._-")[:MAX_NAME_LENGTH]


def user_folder_name(user: Users) -> str:
    """Folder of the user, e.g. 0007_sam.student.

    An existing folder with the number of the user is kept, also if the e-mail changed.
    """

    prefix = f"{user.itid:04d}_"
    root = root_dir()
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and entry.name.startswith(prefix):
                return entry.name
    local_part = (user.email or "").split("@")[0]
    return prefix + (safe_part(local_part) or "user")


def exercise_folder_name(exercise: Exercises) -> str:
    return safe_part(exercise.code) or f"exercise-{exercise.itid}"


def split_filename(filename: str) -> tuple[str, str]:
    """Safe stem and the extension in lower case. Path parts are dropped."""

    name = re.split(r"[\\/]", filename or "")[-1]
    stem, ext = os.path.splitext(name)
    return safe_part(stem) or "file", ext.lower()


def unique_name(folder: Path, stem: str, ext: str) -> str:
    name = stem + ext
    number = 2
    while (folder / name).exists():
        name = f"{stem}-{number}{ext}"
        number += 1
    return name


def file_path(submission: ExerciseSubmissions) -> Path:
    """Path of the file. It must stay in SUBMISSIONS_DIR."""

    root = root_dir().resolve()
    path = (root / submission.folder / submission.stored_name).resolve()
    if not path.is_relative_to(root):
        raise SubmissionError("The file is not in the submissions folder.")
    return path


# ---- content checks ----


def check_content(ext: str, path: Path) -> bool:
    """Does the content fit the extension?"""

    if ext == ".pdf":
        with open(path, "rb") as file:
            return file.read(5) == b"%PDF-"
    if ext == ".docx":
        if not zipfile.is_zipfile(path):
            return False
        try:
            with zipfile.ZipFile(path) as archive:
                return "word/document.xml" in archive.namelist()
        except zipfile.BadZipFile:
            return False
    if ext in (".txt", ".md"):
        data = path.read_bytes()
        if b"\x00" in data:
            return False
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


# ---- submissions of a user ----


def active_submissions(db: Session, user_id: int, exercise_id: int) -> list:
    return (
        db.query(ExerciseSubmissions)
        .filter_by(user_id=user_id, exercise_id=exercise_id, deleted=False)
        .order_by(ExerciseSubmissions.created_at.asc(), ExerciseSubmissions.itid.asc())
        .all()
    )


def all_submissions(db: Session, user_id: int, exercise_id: int) -> list:
    """Also the deleted files (for the admin)"""

    return (
        db.query(ExerciseSubmissions)
        .filter_by(user_id=user_id, exercise_id=exercise_id)
        .order_by(ExerciseSubmissions.created_at.asc(), ExerciseSubmissions.itid.asc())
        .all()
    )


def _store(folder: Path, upload: Upload, ext: str, limit: int) -> tuple:
    """Writes the upload into a temporary file of the folder.

    Returns:
        tuple: path of the temporary file, size in bytes, SHA-256
    """

    digest = hashlib.sha256()
    size = 0
    handle, temp_name = tempfile.mkstemp(dir=folder, prefix=".upload-", suffix=ext)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as target:
            while chunk := upload.file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > limit:
                    raise SubmissionError(f"{upload.filename}: the file is too large.")
                digest.update(chunk)
                target.write(chunk)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path, size, digest.hexdigest()


def save_uploads(
    db: Session, user: Users, exercise: Exercises, uploads: list[Upload]
) -> tuple[list, list]:
    """Saves the files of one upload form.

    Returns:
        tuple: saved submissions, error messages for the user
    """

    if not is_open(effective_deadline(db, exercise, user.itid)):
        raise SubmissionError("The deadline has passed. You can no longer upload.")
    uploads = [upload for upload in uploads if upload.filename]
    if not uploads:
        raise SubmissionError("Choose a file to upload.")

    settings = get_settings()
    free = settings.submission_max_files - len(
        active_submissions(db, user.itid, exercise.itid)
    )
    folder_name = f"{user_folder_name(user)}/{exercise_folder_name(exercise)}"
    folder = root_dir() / folder_name
    budget = max_bytes()
    saved, errors = [], []

    for upload in uploads:
        stem, ext = split_filename(upload.filename)
        if ext not in ALLOWED_TYPES:
            errors.append(f"{upload.filename}: upload a {ALLOWED_TEXT} file.")
            continue
        if free <= 0:
            errors.append(
                f"{upload.filename}: you can submit at most "
                f"{settings.submission_max_files} files for this exercise."
            )
            continue
        folder.mkdir(parents=True, exist_ok=True)
        try:
            temp_path, size, sha256 = _store(folder, upload, ext, budget)
        except SubmissionError as error:
            errors.append(
                str(error)
                + f" One upload can have at most {settings.submission_max_file_mb} MB."
            )
            continue
        if size == 0 or not check_content(ext, temp_path):
            temp_path.unlink(missing_ok=True)
            errors.append(
                f"{upload.filename}: the file is empty or is not a valid {ext[1:].upper()} file."
            )
            continue
        stored_name = unique_name(folder, stem, ext)
        os.replace(temp_path, folder / stored_name)
        submission = ExerciseSubmissions(
            exercise_id=exercise.itid,
            user_id=user.itid,
            original_name=re.split(r"[\\/]", upload.filename)[-1][:255],
            stored_name=stored_name,
            folder=folder_name,
            size_bytes=size,
            sha256=sha256,
            content_type=ALLOWED_TYPES[ext],
        )
        db.add(submission)
        db.commit()
        saved.append(submission)
        budget -= size
        free -= 1
        logger.info(
            "User %s submitted %s for %s (%s bytes)",
            user.itid,
            stored_name,
            exercise.code,
            size,
        )
    return saved, errors


def get_submission(db: Session, submission_id: int) -> ExerciseSubmissions | None:
    return db.query(ExerciseSubmissions).filter_by(itid=submission_id).first()


def delete_submission(db: Session, submission: ExerciseSubmissions) -> None:
    """Removes the file. The row stays, marked as deleted."""

    try:
        file_path(submission).unlink(missing_ok=True)
    except OSError as error:
        logger.error("File %s was not deleted: %s", submission.stored_name, error)
        raise SubmissionError("The file was not deleted. Try again later.")
    submission.deleted = True
    submission.deleted_at = datetime.now()
    db.commit()
    logger.info(
        "Submission %s of user %s was deleted", submission.itid, submission.user_id
    )


def delete_own_submission(
    db: Session, user: Users, exercise: Exercises, submission_id: int
) -> ExerciseSubmissions:
    submission = get_submission(db, submission_id)
    if (
        submission is None
        or submission.deleted
        or submission.user_id != user.itid
        or submission.exercise_id != exercise.itid
    ):
        raise SubmissionError("There is no such file.")
    if not is_open(effective_deadline(db, exercise, user.itid)):
        raise SubmissionError("The deadline has passed. You can no longer delete.")
    delete_submission(db, submission)
    return submission


# ---- overview for the admin ----


def submission_matrix(db: Session, exercises: list, user_ids: list) -> dict:
    """(user_id, exercise_id) -> {"count", "last", "extension"}"""

    cells = {}
    exercise_ids = [exercise.itid for exercise in exercises]
    rows = (
        db.query(ExerciseSubmissions)
        .filter(
            ExerciseSubmissions.deleted.is_(False),
            ExerciseSubmissions.exercise_id.in_(exercise_ids),
            ExerciseSubmissions.user_id.in_(user_ids),
        )
        .all()
    )
    for row in rows:
        cell = cells.setdefault(
            (row.user_id, row.exercise_id),
            {"count": 0, "last": None, "extension": None},
        )
        cell["count"] += 1
        if row.created_at and (cell["last"] is None or row.created_at > cell["last"]):
            cell["last"] = row.created_at
    extensions = (
        db.query(SubmissionExtensions)
        .filter(SubmissionExtensions.exercise_id.in_(exercise_ids))
        .all()
    )
    for extension in extensions:
        cell = cells.setdefault(
            (extension.user_id, extension.exercise_id),
            {"count": 0, "last": None, "extension": None},
        )
        cell["extension"] = extension.deadline
    return cells


def zip_exercise(db: Session, exercise: Exercises) -> tuple[Path, int]:
    """ZIP file with the submitted files of all users: <user folder>/<file>.

    Returns:
        tuple: path of a temporary file (the caller removes it), number of files
    """

    rows = (
        db.query(ExerciseSubmissions)
        .filter_by(exercise_id=exercise.itid, deleted=False)
        .order_by(ExerciseSubmissions.folder, ExerciseSubmissions.stored_name)
        .all()
    )
    handle, temp_name = tempfile.mkstemp(prefix="submissions-", suffix=".zip")
    os.close(handle)
    count = 0
    with zipfile.ZipFile(temp_name, "w", zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            path = file_path(row)
            if not path.is_file():
                logger.warning("Submitted file is missing: %s", path)
                continue
            user_folder = row.folder.split("/")[0]
            archive.write(
                path,
                f"{exercise_folder_name(exercise)}/{user_folder}/{row.stored_name}",
            )
            count += 1
    return Path(temp_name), count


# ---- e-mail ----


def format_size(size: int) -> str:
    if size >= MB:
        return f"{size / MB:.1f} MB"
    return f"{max(size / 1024, 0.1):.1f} KB"


def confirmation_text(
    exercise: Exercises, action: str, files: list, deadline, remaining: list
) -> str:
    lines = [f"Exercise: {exercise.name or exercise.code} ({exercise.code})", ""]
    if action == "upload":
        lines.append("You submitted these files:")
    else:
        lines.append("You deleted these files:")
    for row in files:
        lines.append(
            f"- {row.original_name} ({format_size(row.size_bytes)}, SHA-256 {row.sha256})"
        )
    lines += ["", "Your files for this exercise now:"]
    lines += [f"- {row.original_name}" for row in remaining] or ["- none"]
    if deadline:
        lines += [
            "",
            f"Deadline: {deadline:%d.%m.%Y %H:%M}. Until then you can upload and delete files.",
        ]
    lines += ["", "Time of this e-mail: " + datetime.now().strftime("%d.%m.%Y %H:%M")]
    return "\n".join(lines)


def confirmation_email(
    exercise: Exercises, action: str, files: list, deadline, remaining: list
) -> tuple[str, str]:
    """Subject and text of the confirmation e-mail"""

    subject = (
        f"Submission received: {exercise.code}"
        if action == "upload"
        else f"Submission deleted: {exercise.code}"
    )
    return subject, confirmation_text(exercise, action, files, deadline, remaining)


def send_confirmation(email: str, subject: str, content: str) -> None:
    """Sends the confirmation e-mail. Runs after the response."""

    if not send_email(email, subject, content, get_settings()):
        logger.warning("Confirmation e-mail was not sent: %s", subject)
