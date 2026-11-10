from datetime import datetime

import click
from flask.cli import with_appcontext


@click.command()
@with_appcontext
def create_demo_db():
    """Created a demo database and a read-only user
    $> flask create-demo-db
    """

    from flask import current_app

    from ..main.postgresql_helpers import (
        create_postgresql_readonly_user_for_demo_db,
        init_postgresql_with_demo_user,
    )

    init_postgresql_with_demo_user()
    create_postgresql_readonly_user_for_demo_db(
        readonly_db_user=current_app.config["POSTGRESQL_DEMO_USER_READONLY"],
        readonly_db_password=current_app.config[
            "POSTGRESQL_DEMO_USER_READONLY_PASSWORD"
        ],
    )


@click.command()
@with_appcontext
def grant_public_schema():
    """
    $> flask grant-public-schema
    """

    from flask import current_app

    from ..main.postgresql_helpers import grand_rights_to_own_public_all

    grand_rights_to_own_public_all()


@click.command()
@with_appcontext
@click.option("--database-name", prompt=True, required=True)
@click.option("--database-username", prompt=True, required=True)
# @click.option('--db-password', hide_input=True, prompt=True, required=True)
@click.option("--database-password", prompt=True, required=True)
def create_custom_db(
    database_name: str, database_username: str, database_password: str
):
    """Created a custom database with a given role and user
    $> flask create-custom-db db_name db_user db_password
    """
    from ..main.postgresql_helpers import create_postgresql_db

    create_postgresql_db(database_name, database_username, database_password)


@click.command()
@with_appcontext
def import_data_exercises():
    """Imports the exercises (with their review and bonus parts) from the CSV file
    $> flask import-data-exercises
    """

    click.echo(f"{datetime.now()} start import data for exercises")
    _import_exercises()
    click.echo(f"{datetime.now()} finish import data for exercises")


def _import_exercises(fname_csv: str = "setup/initial_exercises.csv"):
    """Adds the exercises from the CSV file that are not in the database yet"""

    import csv
    import os

    from app.extensions import db
    from app.models import Exercises

    if not os.path.exists(fname_csv):
        click.echo(f"[e] CSV file with the exercises was not found: {fname_csv}")
        return

    def to_bool(value: str) -> bool:
        return (value or "").strip().lower() == "true"

    def to_value(value: str, convert):
        value = (value or "").strip()
        return convert(value) if value else None

    with open(fname_csv, newline="", encoding="utf-8") as csvfile:
        for row in csv.DictReader(csvfile, delimiter=";"):
            code = (row["code"] or "").strip()
            if not code or db.session.query(Exercises).filter_by(code=code).first():
                continue
            db.session.add(
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
    db.session.commit()
