from datetime import datetime

import pytest
from click.testing import CliRunner
from sqlalchemy import inspect

from app.cli import cli
from app.cli.database import import_exercises
from app.database import get_engine, init_engine, session_scope
from app.exercises import exercise_csv_row
from app.models import Exercises
from tests.conftest import add_postgresql, add_user

EXERCISES_CSV = """code;name;description;year;visible;exercise_order;submission_deadline;has_review;has_bonus;bonus_max_points;has_submission;submission_email
EX1;Data model;First exercise;2026;true;1;2026-11-30T23:59:00;true;true;5;true;true
EX2;ETL process;;2026;false;2;;true;false;;false;false
;No code;;;;;;;;;;
"""
OLD_EXERCISES_CSV = """code;name;description;year;visible;exercise_order;submission_deadline;has_review;has_bonus;bonus_max_points
EX1;Data model;First exercise;2026;true;1;2026-11-30T23:59:00;true;true;5
"""


@pytest.fixture
def runner(settings):
    init_engine(settings.database_url)
    return CliRunner()


@pytest.fixture
def exercises_file(tmp_path):
    path = tmp_path / "exercises.csv"
    path.write_text(EXERCISES_CSV, encoding="utf-8")
    return str(path)


def test_help_lists_all_commands(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in [
        "db-upgrade",
        "db-migrate",
        "import-data-exercises",
        "export-data-exercises",
        "create-demo-db",
        "create-custom-db",
        "grant-public-schema",
        "nginx-config",
    ]:
        assert command in result.output


def test_db_upgrade_creates_the_database(runner):
    result = runner.invoke(cli, ["db-upgrade"])
    assert result.exit_code == 0, result.output
    tables = inspect(get_engine()).get_table_names()
    assert {"users", "exercises", "background_tasks", "alembic_version"} <= set(tables)
    assert runner.invoke(cli, ["db-upgrade"]).exit_code == 0


def test_db_migrate_creates_no_empty_migration(runner):
    from app.config import BASE_DIR

    versions = BASE_DIR / "migrations" / "versions"
    before = sorted(versions.glob("*.py"))
    runner.invoke(cli, ["db-upgrade"])
    result = runner.invoke(cli, ["db-migrate", "-m", "nothing changed"])
    assert result.exit_code == 0, result.output
    assert "no migration was created" in result.output
    assert sorted(versions.glob("*.py")) == before


def test_models_and_migrations_are_in_sync(runner):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.database import Base

    runner.invoke(cli, ["db-upgrade"])
    with get_engine().connect() as connection:
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []


def test_import_exercises(runner, exercises_file):
    runner.invoke(cli, ["db-upgrade"])
    result = runner.invoke(cli, ["import-data-exercises", "--file", exercises_file])
    assert result.exit_code == 0, result.output
    assert "new exercises: 2" in result.output

    with session_scope() as db:
        first, second = db.query(Exercises).order_by(Exercises.exercise_order).all()
        assert (first.code, first.name, first.year, first.visible) == (
            "EX1",
            "Data model",
            2026,
            True,
        )
        assert first.submission_deadline.isoformat() == "2026-11-30T23:59:00"
        assert (first.has_review, first.has_bonus, first.bonus_max_points) == (
            True,
            True,
            5.0,
        )
        assert (second.description, second.visible, second.bonus_max_points) == (
            None,
            False,
            None,
        )
        assert (first.has_submission, first.submission_email) == (True, True)
        assert (second.has_submission, second.submission_email) == (False, False)

    again = runner.invoke(cli, ["import-data-exercises", "--file", exercises_file])
    assert "new exercises: 0" in again.output


def test_import_exercises_without_file(runner):
    result = runner.invoke(cli, ["import-data-exercises", "--file", "no-such-file.csv"])
    assert result.exit_code == 0
    assert "was not found" in result.output


def test_import_exercises_rejects_the_old_format(runner, tmp_path):
    runner.invoke(cli, ["db-upgrade"])
    path = tmp_path / "old.csv"
    path.write_text(OLD_EXERCISES_CSV, encoding="utf-8")
    result = runner.invoke(cli, ["import-data-exercises", "--file", str(path)])
    # the container still starts (docker-entrypoint.sh)
    assert result.exit_code == 0
    assert "has_submission, submission_email" in result.output
    with session_scope() as db:
        assert db.query(Exercises).count() == 0


def test_sample_exercises_have_all_columns():
    from app.cli.database import missing_exercise_columns
    from app.config import BASE_DIR

    assert (
        missing_exercise_columns(BASE_DIR / "samples" / "initial_exercises.csv") == []
    )


def test_import_exercises_function(db, exercises_file):
    assert import_exercises(db, exercises_file) == (2, 0)


def test_create_demo_db(runner, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.cli.database.postgresql.init_postgresql_with_demo_user",
        lambda: calls.append("demo") or True,
    )
    monkeypatch.setattr(
        "app.cli.database.postgresql.create_postgresql_readonly_user_for_demo_db",
        lambda **kwargs: calls.append(kwargs) or True,
    )
    result = runner.invoke(cli, ["create-demo-db"])
    assert result.exit_code == 0
    assert "db_demo" in result.output
    assert calls == [
        "demo",
        {"readonly_db_user": "db_user_demo_ro", "readonly_db_password": "postgres"},
    ]


def test_create_demo_db_reports_a_failure(runner, monkeypatch):
    monkeypatch.setattr(
        "app.cli.database.postgresql.init_postgresql_with_demo_user", lambda: False
    )
    monkeypatch.setattr(
        "app.cli.database.postgresql.create_postgresql_readonly_user_for_demo_db",
        lambda **kwargs: True,
    )
    result = runner.invoke(cli, ["create-demo-db"])
    assert result.exit_code == 1
    assert "was not created" in result.output


def test_create_custom_db(runner, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.cli.database.postgresql.create_postgresql_db",
        lambda *args: calls.append(args) or True,
    )
    args = [
        "create-custom-db",
        "--database-name",
        "d",
        "--database-username",
        "u",
        "--database-password",
        "p",
    ]
    assert runner.invoke(cli, args).exit_code == 0
    assert calls == [("d", "u", "p")]

    monkeypatch.setattr(
        "app.cli.database.postgresql.create_postgresql_db", lambda *args: False
    )
    assert runner.invoke(cli, args).exit_code == 1


def test_create_custom_db_asks_for_missing_values(runner, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.cli.database.postgresql.create_postgresql_db",
        lambda *args: calls.append(args) or True,
    )
    result = runner.invoke(cli, ["create-custom-db"], input="d\nu\np\n")
    assert result.exit_code == 0
    assert calls == [("d", "u", "p")]


def test_grant_public_schema(app, db, monkeypatch):
    with_db = add_user(db)
    add_postgresql(db, with_db)
    add_user(db, email="other@uni.example", number=2)
    calls = []
    monkeypatch.setattr(
        "app.cli.database.postgresql.grant_rights_to_own_public_schema",
        lambda *args: calls.append(args),
    )
    result = CliRunner().invoke(cli, ["grant-public-schema"])
    assert result.exit_code == 0, result.output
    assert calls == [("bicourse_db_01", "bicourse_user_01")]
    assert "no PostgreSQL database" in result.output


def test_nginx_config(runner, tmp_path):
    result = runner.invoke(
        cli, ["nginx-config", "-t", str(tmp_path), "-n", "3", "-d", "/auth"]
    )
    assert result.exit_code == 0, result.output

    openrefine = (tmp_path / "nginx_part_openrefine.config").read_text()
    assert openrefine.count("location /openrefine/") == 3
    assert "location /openrefine/4003/ {" in openrefine
    assert "auth_basic_user_file /auth/4001.htpasswd;" in openrefine
    assert "proxy_pass http://openrefine-4002/$1$is_args$args;" in openrefine

    nifi = (tmp_path / "nginx_part_nifi.config").read_text()
    assert nifi.count("location /nifi/") == 3
    assert "proxy_pass http://127.0.0.1:6001/;" in nifi


def test_nginx_config_for_one_service(runner, tmp_path):
    result = runner.invoke(
        cli, ["nginx-config", "-s", "nifi", "-t", str(tmp_path), "-n", "1"]
    )
    assert result.exit_code == 0
    assert (tmp_path / "nginx_part_nifi.config").exists()
    assert not (tmp_path / "nginx_part_openrefine.config").exists()


def test_committed_nginx_config_matches_the_generator(runner, tmp_path):
    from app.config import BASE_DIR

    runner.invoke(cli, ["nginx-config", "-t", str(tmp_path)])
    for name in ("nginx_part_openrefine.config", "nginx_part_nifi.config"):
        committed = (BASE_DIR / "provision" / "nginx" / name).read_text()
        assert (tmp_path / name).read_text() == committed, name


def test_show_config_hides_secrets(runner, settings):
    result = runner.invoke(cli, ["show-config"])
    assert result.exit_code == 0, result.output
    assert "SERVER_FQDN=mtas.example.org" in result.output
    assert "SYSTEM_ADMINS=ada.admin@uni.example" in result.output
    assert "test-secret-key" not in result.output
    assert "PASSWORD" not in result.output


def test_check_mail(runner, monkeypatch):
    from tests.test_emails import FakeSMTP

    monkeypatch.setattr("app.emails.smtplib.SMTP", FakeSMTP)
    result = runner.invoke(cli, ["check-mail", "--to", "me@x.org"])
    assert result.exit_code == 0, result.output
    assert "Connection and login work." in result.output
    assert "Test e-mail was sent to me@x.org." in result.output


def test_check_mail_names_the_problem(runner, monkeypatch):
    def no_route(*_args, **_kwargs):
        raise OSError(113, "No route to host")

    monkeypatch.setattr("app.emails.smtplib.SMTP", no_route)
    result = runner.invoke(cli, ["check-mail"])
    assert result.exit_code == 1
    assert "Cannot connect to the SMTP server localhost:587" in result.output
    assert "VPN" in result.output


def test_export_and_import_give_the_same_exercises(runner, tmp_path, monkeypatch):
    from app.cli.database import missing_exercise_columns

    runner.invoke(cli, ["db-upgrade"])
    with session_scope() as db:
        db.add(
            Exercises(
                code="EX7",
                name='Report "final"; part 1',
                description="Line one;\nline two",
                year=2026,
                visible=False,
                exercise_order=7,
                submission_deadline=datetime(2026, 12, 24, 18, 30),
                has_review=False,
                has_bonus=True,
                bonus_max_points=2.5,
                has_submission=True,
                submission_email=True,
            )
        )
        db.add(Exercises(code="EX8", name="Plain", exercise_order=8))
        db.commit()

    path = tmp_path / "export.csv"
    result = runner.invoke(cli, ["export-data-exercises", "--file", str(path)])
    assert result.exit_code == 0, result.output
    assert "2 rows" in result.output
    assert missing_exercise_columns(str(path)) == []

    with session_scope() as db:
        before = [exercise_csv_row(e) for e in db.query(Exercises).all()]
        db.query(Exercises).delete()
        db.commit()
        assert import_exercises(db, str(path)) == (2, 0)
        after = [exercise_csv_row(e) for e in db.query(Exercises).all()]
    assert sorted(after, key=lambda r: r["code"]) == sorted(
        before, key=lambda r: r["code"]
    )

    # without --file: into the backup folder, the setup file stays
    monkeypatch.setattr("app.cli.database.BACKUP_DIR", tmp_path / "backups")
    result = runner.invoke(cli, ["export-data-exercises"])
    assert result.exit_code == 0, result.output
    [backup] = (tmp_path / "backups").glob("*-initial_exercises.csv")
    assert backup.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


def test_import_with_update_changes_existing_exercises(
    runner, exercises_file, tmp_path
):
    runner.invoke(cli, ["db-upgrade"])
    runner.invoke(cli, ["import-data-exercises", "--file", exercises_file])
    changed = tmp_path / "changed.csv"
    changed.write_text(
        EXERCISES_CSV.replace("Data model;First exercise", "Data model 2;Changed")
        + "EX3;New;;2026;true;3;;true;false;;false;false\n",
        encoding="utf-8",
    )

    plain = runner.invoke(cli, ["import-data-exercises", "--file", str(changed)])
    assert "new exercises: 1" in plain.output
    with session_scope() as db:
        assert db.query(Exercises).filter_by(code="EX1").one().name == "Data model"

    result = runner.invoke(
        cli, ["import-data-exercises", "--file", str(changed), "--update"]
    )
    assert result.exit_code == 0, result.output
    assert "new exercises: 0" in result.output
    assert "changed exercises: 3" in result.output
    with session_scope() as db:
        first = db.query(Exercises).filter_by(code="EX1").one()
        assert (first.name, first.description) == ("Data model 2", "Changed")


def test_db_backup_also_saves_the_submitted_files(runner, settings, tmp_path):
    import tarfile

    runner.invoke(cli, ["db-upgrade"])
    report = settings.submissions_dir / "0001_sam" / "EX1" / "report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF-1.7")

    target = tmp_path / "backups"
    result = runner.invoke(cli, ["db-backup", "--dir", str(target)])
    assert result.exit_code == 0, result.output
    [archive] = target.glob("*-submissions.tar.gz")
    with tarfile.open(archive) as tar:
        assert "submissions/0001_sam/EX1/report.pdf" in tar.getnames()
    assert len(list(target.glob("*-test.db"))) == 1

    only_db = tmp_path / "only-db"
    result = runner.invoke(cli, ["db-backup", "--dir", str(only_db), "--no-files"])
    assert result.exit_code == 0, result.output
    assert not list(only_db.glob("*.tar.gz"))


def test_db_backup_without_submissions_folder(runner, tmp_path):
    runner.invoke(cli, ["db-upgrade"])
    result = runner.invoke(cli, ["db-backup", "--dir", str(tmp_path / "b")])
    assert result.exit_code == 0, result.output
    assert "nothing to back up" in result.output


def test_prune_backups_keeps_the_newest(tmp_path):
    from app.database import prune_backups

    names = [f"2026110{day}-120000-test.db" for day in range(1, 6)]
    for name in names + ["20261101-120000-submissions.tar.gz", "notes.txt"]:
        (tmp_path / name).write_text("x")
    removed = prune_backups(tmp_path, "test.db", keep=2)
    assert sorted(path.name for path in removed) == names[:3]
    left = sorted(path.name for path in tmp_path.iterdir())
    assert left == [
        "20261101-120000-submissions.tar.gz",
        names[3],
        names[4],
        "notes.txt",
    ]
    assert prune_backups(tmp_path, "test.db", keep=0) == []


def test_db_backup_deletes_old_backups(runner, settings, tmp_path):
    runner.invoke(cli, ["db-upgrade"])
    settings.submissions_dir.mkdir(parents=True)
    target = tmp_path / "backups"
    target.mkdir()
    for day in range(1, 4):
        (target / f"2026010{day}-120000-test.db").write_text("old")
        (target / f"2026010{day}-120000-submissions.tar.gz").write_text("old")
    (target / "20260101-120000-initial_exercises.csv").write_text("keep")

    result = runner.invoke(cli, ["db-backup", "--dir", str(target), "--keep", "2"])
    assert result.exit_code == 0, result.output
    assert len(list(target.glob("*-test.db"))) == 2
    assert len(list(target.glob("*-submissions.tar.gz"))) == 2
    assert (target / "20260101-120000-initial_exercises.csv").exists()
    assert "old backup deleted: 20260102-120000-test.db" in result.output
