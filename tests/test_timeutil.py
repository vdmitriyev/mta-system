"""Times are stored in UTC and shown in the local time of the server"""

from datetime import datetime

from alembic import command
from sqlalchemy import text

from app.cli.database import alembic_config, import_exercises
from app.database import get_engine, init_engine
from app.exercises import exercise_csv_row
from app.models import AdminActions, Exercises
from app.timeutil import local_text, to_local, to_utc
from tests.conftest import add_exercise, post


def test_conversion_in_winter_and_summer(berlin):
    assert to_utc(datetime(2026, 11, 30, 23, 59)) == datetime(2026, 11, 30, 22, 59)
    assert to_utc(datetime(2026, 7, 1, 12, 0)) == datetime(2026, 7, 1, 10, 0)
    assert to_local(datetime(2026, 11, 30, 22, 59)) == datetime(2026, 11, 30, 23, 59)
    assert local_text(datetime(2026, 7, 1, 10, 0)) == "01.07.2026 12:00"
    assert local_text(None) == "" and to_utc(None) is None


def test_deadline_is_entered_and_shown_in_local_time(berlin, admin_client, db):
    response = post(
        admin_client,
        "/mtas-admin/exercises/edit",
        {"code": "EX09", "name": "Report", "submission_deadline": "30.11.2026 23:59"},
    )
    assert response.status_code == 303
    exercise = db.query(Exercises).filter_by(code="EX09").one()
    assert exercise.submission_deadline == datetime(2026, 11, 30, 22, 59)
    form = admin_client.get("/mtas-admin/exercises/edit?code=EX09").text
    assert 'value="30.11.2026 23:59"' in form
    assert "30.11.2026 23:59" in admin_client.get("/mtas-admin/exercises").text


def test_csv_has_local_time_and_the_import_stores_utc(berlin, db, tmp_path):
    exercise = add_exercise(
        db, "EX1", submission_deadline=datetime(2026, 11, 30, 22, 59)
    )
    assert exercise_csv_row(exercise)["submission_deadline"] == "2026-11-30T23:59:00"
    path = tmp_path / "exercises.csv"
    path.write_text(
        "code;name;description;year;visible;exercise_order;submission_deadline;"
        "has_review;has_bonus;bonus_max_points;has_submission;submission_email\n"
        "EX2;ETL;;2026;true;2;2026-12-15T12:00:00;true;false;;true;false\n",
        encoding="utf-8",
    )
    import_exercises(db, str(path))
    second = db.query(Exercises).filter_by(code="EX2").one()
    assert second.submission_deadline == datetime(2026, 12, 15, 11, 0)


def test_admin_log_shows_local_time(berlin, admin_client, db, admin):
    db.add(
        AdminActions(
            admin_id=admin.itid,
            action="review",
            created_at=datetime(2026, 7, 1, 10, 0, 5),
        )
    )
    db.commit()
    page = admin_client.get("/mtas-admin/actions").text
    assert "01.07.2026 12:00:05" in page and "UTC" not in page


def test_migration_turns_local_times_into_utc(berlin, settings):
    init_engine(settings.database_url)
    config = alembic_config()
    command.upgrade(config, "b8d4f0a2c6e3")
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "INSERT INTO exercises (code, name, visible, has_review, has_bonus, "
                "has_submission, submission_email, submission_deadline) VALUES "
                "('EX1', 'x', 1, 1, 0, 1, 0, '2026-11-30 23:59:00.000000')"
            )
        )
    command.upgrade(config, "head")
    with get_engine().connect() as connection:
        value = connection.execute(
            text("SELECT submission_deadline FROM exercises")
        ).scalar()
    assert str(value).startswith("2026-11-30 22:59:00")
    command.downgrade(config, "b8d4f0a2c6e3")
    with get_engine().connect() as connection:
        value = connection.execute(
            text("SELECT submission_deadline FROM exercises")
        ).scalar()
    assert str(value).startswith("2026-11-30 23:59:00")
