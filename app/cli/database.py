import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import click
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.database import backup_sqlite, pack_folder, prune_backups, session_scope
from app.exercises import EXERCISE_COLUMNS, exercises_csv, get_exercises
from app.models import Exercises
from app.services import postgresql
from app.users import course_users, get_user_services

DEFAULT_EXERCISES_FILE = os.path.join("setup", "initial_exercises.csv")
BACKUP_DIR = BASE_DIR / ".backups"


def alembic_config() -> Config:
    config = Config(str(BASE_DIR / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return config


@click.command("db-upgrade")
def db_upgrade():
    """Creates the SQLite database or updates it to the newest version"""

    command.upgrade(alembic_config(), "head")
    click.echo("[i] database is up to date")


@click.command("db-backup")
@click.option(
    "--dir",
    "backup_dir",
    type=click.Path(file_okay=False),
    default=str(BACKUP_DIR),
    show_default=True,
)
@click.option(
    "--no-files", is_flag=True, help="Only the database, not the folders with files"
)
@click.option(
    "--keep",
    type=click.IntRange(min=0),
    default=None,
    help="Backups of each kind that stay, the oldest are deleted. 0: all stay. "
    "Default: BACKUP_KEEP",
)
def db_backup(backup_dir: str, no_files: bool, keep: int | None):
    """Copies the SQLite database and the folders with files to the backup folder"""

    settings = get_settings()
    target_dir = Path(backup_dir)
    try:
        target = backup_sqlite(settings.mtas_db_path, target_dir)
    except (OSError, sqlite3.Error) as error:
        raise click.ClickException(f"No backup: {error}")
    click.echo(f"[i] backup: {target}")
    names = [settings.mtas_db_path.name]
    if not no_files:
        for folder, name in (
            (settings.submissions_dir, "submissions"),
            (settings.downloads_dir, "downloads"),
        ):
            try:
                archive = pack_folder(folder, target_dir, name)
            except OSError as error:
                raise click.ClickException(f"No backup of {name}: {error}")
            if archive is None:
                click.echo(f"[i] no folder {folder}, nothing to back up")
            else:
                click.echo(f"[i] backup: {archive}")
                names.append(f"{name}.tar.gz")
    keep = settings.backup_keep if keep is None else keep
    for name in names:
        for path in prune_backups(target_dir, name, keep):
            click.echo(f"[i] old backup deleted: {path.name}")


@click.command("db-migrate")
@click.option("--message", "-m", default="schema change", show_default=True)
def db_migrate(message: str):
    """Creates a new migration from the changes in app/models.py"""

    created = []

    def skip_empty(_context, _revision, directives):
        # without changes, Alembic would write an empty migration
        if directives[0].upgrade_ops.is_empty():
            directives[:] = []
        else:
            created.append(directives[0].rev_id)

    command.revision(
        alembic_config(),
        message=message,
        autogenerate=True,
        process_revision_directives=skip_empty,
    )
    if created:
        click.echo(f"[i] new migration: {created[0]}")
    else:
        click.echo("[i] no changes in app/models.py: no migration was created")


@click.command("import-data-exercises")
@click.option(
    "--file", "-f", "fname_csv", default=DEFAULT_EXERCISES_FILE, show_default=True
)
@click.option(
    "--update",
    is_flag=True,
    help="Also change the exercises that exist, to the values of the file",
)
def import_data_exercises(fname_csv: str, update: bool):
    """Imports the exercises (with their review, bonus and submission parts) from the CSV file"""

    if not os.path.exists(fname_csv):
        click.echo(f"[e] CSV file with the exercises was not found: {fname_csv}")
        return
    missing = missing_exercise_columns(fname_csv)
    if missing:
        click.echo(
            f"[e] {fname_csv} is in an old format. Add the columns "
            f"{', '.join(missing)} (see samples/initial_exercises.csv). "
            "No exercises were imported."
        )
        return
    with session_scope() as db:
        added, updated = import_exercises(db, fname_csv, update=update)
    click.echo(f"[i] new exercises: {added}")
    if update:
        click.echo(f"[i] changed exercises: {updated}")


@click.command("export-data-exercises")
@click.option(
    "--file",
    "-f",
    "fname_csv",
    default=None,
    help="Target file. Default: .backups/<date>-<time>-initial_exercises.csv",
)
def export_data_exercises(fname_csv: str | None):
    """Writes all exercises into a CSV file, in the format of import-data-exercises"""

    if fname_csv is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname_csv = str(BACKUP_DIR / f"{stamp}-initial_exercises.csv")
    os.makedirs(os.path.dirname(os.path.abspath(fname_csv)), exist_ok=True)
    with session_scope() as db:
        content = exercises_csv(db)
        count = len(get_exercises(db))
    with open(fname_csv, "w", newline="", encoding="utf-8") as csvfile:
        csvfile.write(content)
    click.echo(f"[i] exercises: {count} rows -> {fname_csv}")


def missing_exercise_columns(fname_csv: str) -> list:
    with open(fname_csv, newline="", encoding="utf-8") as csvfile:
        header = next(csv.reader(csvfile, delimiter=";"), [])
    return [column for column in EXERCISE_COLUMNS if column not in header]


def import_exercises(db: Session, fname_csv: str, update: bool = False) -> tuple:
    """Adds the exercises from the CSV file that are not in the database yet.

    update: also sets the values of the file on the exercises that exist.
    Returns (added, updated).
    """

    def to_bool(value: str) -> bool:
        return (value or "").strip().lower() == "true"

    def to_value(value: str, convert):
        value = (value or "").strip()
        return convert(value) if value else None

    added = updated = 0
    with open(fname_csv, newline="", encoding="utf-8") as csvfile:
        for row in csv.DictReader(csvfile, delimiter=";"):
            code = (row["code"] or "").strip()
            if not code:
                continue
            exercise = db.query(Exercises).filter_by(code=code).first()
            if exercise is not None and not update:
                continue
            values = {
                "name": row["name"].strip(),
                "description": row["description"].strip() or None,
                "year": to_value(row["year"], int),
                "visible": to_bool(row["visible"]),
                "exercise_order": to_value(row["exercise_order"], int),
                "submission_deadline": to_value(
                    row["submission_deadline"], datetime.fromisoformat
                ),
                "has_review": to_bool(row["has_review"]),
                "has_bonus": to_bool(row["has_bonus"]),
                "bonus_max_points": to_value(row["bonus_max_points"], float),
                "has_submission": to_bool(row["has_submission"]),
                "submission_email": to_bool(row["submission_email"]),
            }
            if exercise is None:
                db.add(Exercises(code=code, **values))
                added += 1
            else:
                for key, value in values.items():
                    setattr(exercise, key, value)
                updated += 1
    db.commit()
    return added, updated


@click.command("create-demo-db")
def create_demo_db():
    """Creates the demo database and a read-only user in the PostgreSQL service"""

    settings = get_settings()
    created = postgresql.init_postgresql_with_demo_user()
    readonly = postgresql.create_postgresql_readonly_user_for_demo_db(
        readonly_db_user=settings.postgresql_demo_user_readonly,
        readonly_db_password=settings.postgresql_demo_user_readonly_password.get_secret_value(),
    )
    if not (created and readonly):
        raise click.ClickException("Demo database was not created. See the log file.")
    click.echo(f"[i] demo database: {settings.postgresql_demo_db}")


@click.command("create-custom-db")
@click.option("--database-name", prompt=True, required=True)
@click.option("--database-username", prompt=True, required=True)
@click.option("--database-password", prompt=True, required=True)
def create_custom_db(
    database_name: str, database_username: str, database_password: str
):
    """Creates a database with its own user in the PostgreSQL service"""

    if not postgresql.create_postgresql_db(
        database_name, database_username, database_password
    ):
        raise click.ClickException("Database was not created. See the log file.")
    click.echo(f"[i] database: {database_name}")


@click.command("grant-public-schema")
def grant_public_schema():
    """Lets all users of the course create tables in their PostgreSQL database"""

    with session_scope() as db:
        for user in course_users(db):
            entry = get_user_services(db, user.itid).get("postgresql")
            if entry is None:
                click.echo(f"[w] no PostgreSQL database: {user.internal_email}")
                continue
            postgresql.grant_rights_to_own_public_schema(
                entry.postgresql_db, entry.postgresql_user
            )
            click.echo(f"[i] granted: {entry.postgresql_db}")
