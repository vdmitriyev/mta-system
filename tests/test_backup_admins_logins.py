"""Database backup, accounts of the admins, login history, user of a background task"""

import re
import sqlite3

from click.testing import CliRunner

from app.cli import cli
from app.database import backup_sqlite
from app.models import BackgroundTask, LoginHistory, Users
from app.tasks import enqueue, run_task
from app.users import find_user_by_email, register_user_task
from tests.conftest import ADMIN_EMAIL, STUDENT_EMAIL, login, post


def test_backup_has_date_and_time_in_front(tmp_path):
    db_file = tmp_path / "app.db"
    with sqlite3.connect(db_file) as connection:
        connection.execute("CREATE TABLE t (x)")
        connection.execute("INSERT INTO t VALUES (42)")
    connection.close()

    target = backup_sqlite(db_file, tmp_path / ".backups")

    assert target.parent == tmp_path / ".backups"
    assert re.fullmatch(r"\d{8}-\d{6}-app\.db", target.name)
    copy = sqlite3.connect(target)
    assert copy.execute("SELECT x FROM t").fetchall() == [(42,)]
    copy.close()


def test_backup_without_database_fails(tmp_path):
    try:
        backup_sqlite(tmp_path / "missing.db", tmp_path / ".backups")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")
    assert not (tmp_path / "missing.db").exists()


def test_db_backup_command(db, settings, tmp_path):
    result = CliRunner().invoke(cli, ["db-backup", "--dir", str(tmp_path / "b")])
    assert result.exit_code == 0, result.output
    files = list((tmp_path / "b").iterdir())
    assert len(files) == 1 and files[0].name.endswith("-test.db")


def test_create_admins_creates_prints_and_sends(db, no_email):
    result = CliRunner().invoke(cli, ["create-admins"])
    assert result.exit_code == 0, result.output

    admin = find_user_by_email(db, ADMIN_EMAIL)
    assert admin is not None
    assert f"{ADMIN_EMAIL} (created, user_id {admin.itid})" in result.output
    assert f"PIN:        {admin.pin}" in result.output
    assert "login?uHash=" in result.output
    assert "E-mail:     sent" in result.output
    assert [mail["to"] for mail in no_email] == [ADMIN_EMAIL]


def test_create_admins_keeps_existing_accounts(db, admin, no_email):
    result = CliRunner().invoke(cli, ["create-admins", "--no-mail"])
    assert result.exit_code == 0, result.output
    assert f"{ADMIN_EMAIL} (exists, user_id {admin.itid})" in result.output
    assert db.query(Users).filter(Users.email == ADMIN_EMAIL).count() == 1
    assert no_email == []


def test_create_admins_needs_system_admins(db, use_settings):
    use_settings(SYSTEM_ADMINS="")
    result = CliRunner().invoke(cli, ["create-admins"])
    assert result.exit_code != 0
    assert "SYSTEM_ADMINS is empty" in result.output


def test_logins_are_stored_with_the_user_id(client, db, student):
    login(client)
    post(client, "/logout", {})
    post(client, "/login", {"email": STUDENT_EMAIL, "pin": "0000"}, token_from="/login")
    post(
        client,
        "/login",
        {"email": "nobody@uni.example", "pin": "0000"},
        token_from="/login",
    )
    client.get(f"/login?uHash={student.url_hash}&pHash={student.pin_hash}")

    rows = [
        (row.user_id, row.method, row.result)
        for row in db.query(LoginHistory).order_by(LoginHistory.itid)
    ]
    assert rows == [
        (student.itid, "form", "success"),
        (student.itid, "form", "failed"),
        (None, "form", "failed"),
        (student.itid, "link", "success"),
    ]


def test_admin_sees_the_login_history(admin_client, db, admin, student):
    db.add(LoginHistory(user_id=student.itid, method="link", result="failed"))
    db.commit()

    text = admin_client.get("/mtas-admin/logins").text
    assert f'href="/mtas-admin/logins?user_id={student.itid}"' in text
    assert "login link" in text and "failed" in text
    assert STUDENT_EMAIL not in text

    only = admin_client.get(f"/mtas-admin/logins?user_id={student.itid}").text
    assert f"Only user_id <strong>{student.itid}</strong>" in only
    assert f'logins?user_id={admin.itid}"' not in only


def test_students_cannot_see_the_login_history(student_client):
    response = student_client.get("/mtas-admin/logins", follow_redirects=False)
    assert response.status_code == 403


def test_registration_task_stores_the_new_user(db):
    from fastapi import BackgroundTasks

    task = enqueue(
        BackgroundTasks(), db, "registration", register_user_task, "new@uni.example"
    )
    run_task(task.public_id, register_user_task, "new@uni.example")

    db.expire_all()
    stored = db.query(BackgroundTask).filter_by(public_id=task.public_id).one()
    user = find_user_by_email(db, "new@uni.example")
    assert stored.status == "done"
    assert stored.about_user_id == user.itid


def test_overview_shows_the_user_id_of_a_task(admin_client, db, student):
    db.add(
        BackgroundTask(
            public_id="x" * 32,
            kind="import:demo",
            about_user_id=student.itid,
            status="done",
            message="Imported",
        )
    )
    db.commit()
    text = admin_client.get("/mtas-admin/").text
    assert f'<span class="badge">user_id {student.itid}</span> Imported' in text
