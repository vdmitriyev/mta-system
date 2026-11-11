import csv
import os
from datetime import datetime

import click
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.database import session_scope
from app.models import Exercises
from app.services import postgresql
from app.users import course_users, get_user_services

DEFAULT_EXERCISES_FILE = os.path.join("setup", "initial_exercises.csv")


def alembic_config() -> Config:
    config = Config(str(BASE_DIR / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return config


@click.command("db-upgrade")
def db_upgrade():
    """Creates the SQLite database or updates it to the newest version"""

    command.upgrade(alembic_config(), "head")
    click.echo("[i] database is up to date")


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
def import_data_exercises(fname_csv: str):
    """Imports the exercises (with their review and bonus parts) from the CSV file"""

    if not os.path.exists(fname_csv):
        click.echo(f"[e] CSV file with the exercises was not found: {fname_csv}")
        return
    with session_scope() as db:
        added = import_exercises(db, fname_csv)
    click.echo(f"[i] new exercises: {added}")


def import_exercises(db: Session, fname_csv: str) -> int:
    """Adds the exercises from the CSV file that are not in the database yet"""

    def to_bool(value: str) -> bool:
        return (value or "").strip().lower() == "true"

    def to_value(value: str, convert):
        value = (value or "").strip()
        return convert(value) if value else None

    added = 0
    with open(fname_csv, newline="", encoding="utf-8") as csvfile:
        for row in csv.DictReader(csvfile, delimiter=";"):
            code = (row["code"] or "").strip()
            if not code or db.query(Exercises).filter_by(code=code).first():
                continue
            db.add(
                Exercises(
                    code=code,
                    name=row["name"].strip(),
                    description=row["description"].strip() or None,
                    year=to_value(row["year"], int),
                    visible=to_bool(row["visible"]),
                    exercise_order=to_value(row["exercise_order"], int),
                    submission_deadline=to_value(
                        row["submission_deadline"], datetime.fromisoformat
                    ),
                    has_review=to_bool(row["has_review"]),
                    has_bonus=to_bool(row["has_bonus"]),
                    bonus_max_points=to_value(row["bonus_max_points"], float),
                )
            )
            added += 1
    db.commit()
    return added


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
