"""Admin page Downloads and the page Downloads of the users"""

import io
import zipfile

import pytest

from app import downloads
from app.models import AdminActions, Downloads, ExerciseBonusPoints
from app.visibility import change_ui_visibility_settings
from tests.conftest import (
    ADMIN_EMAIL,
    add_exercise,
    add_user,
    csrf_token,
    login,
    post,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.csv", "a;b\n1;2\n")
    return buffer.getvalue()


def add_file(client, name, content, **fields):
    data = {"csrf_token": csrf_token(client, "/about"), "visible": "on", **fields}
    return client.post(
        "/mtas-admin/downloads/add",
        data=data,
        files={"file": (name, content, "application/octet-stream")},
        follow_redirects=False,
    )


def items(db) -> list:
    db.expire_all()
    return downloads.list_downloads(db)


def test_admin_adds_files_of_all_types(admin_client, db, settings):
    add_exercise(db, "EX2", "ETL", bonus_max_points=5.0)
    for name, content in (
        ("task.pdf", PDF),
        ("data.zip", zip_bytes()),
        ("readme.md", b"# Task\n"),
        ("notes.txt", b"notes\n"),
        ("schema.sql", b"CREATE TABLE a (id int);\n"),
    ):
        response = add_file(admin_client, name, content, exercise="EX2")
        assert response.status_code == 303
    rows = items(db)
    assert [row.original_name for row in rows] == [
        "task.pdf",
        "data.zip",
        "readme.md",
        "notes.txt",
        "schema.sql",
    ]
    assert [row.sort_order for row in rows] == [1, 2, 3, 4, 5]
    assert rows[0].title == "task.pdf" and rows[0].exercise_id is not None
    assert (settings.downloads_dir / "task.pdf").read_bytes() == PDF
    assert db.query(AdminActions).filter_by(action="download_added").count() == 5
    page = admin_client.get("/mtas-admin/downloads").text
    assert "schema.sql" in page and "The users do not see the page Downloads" in page


@pytest.mark.parametrize(
    "name, content, message",
    [
        ("tool.exe", b"MZ", "only PDF, ZIP, MD, TXT or SQL"),
        ("fake.pdf", b"not a pdf", "not a PDF file"),
        ("fake.zip", b"not a zip", "not a ZIP file"),
        ("binary.sql", b"\x00\x01", "not a SQL file"),
        ("empty.txt", b"", "empty"),
    ],
)
def test_wrong_files_are_rejected(admin_client, db, settings, name, content, message):
    response = add_file(admin_client, name, content)
    assert response.status_code == 303
    assert message in admin_client.get("/mtas-admin/downloads").text
    assert items(db) == []
    assert not any(settings.downloads_dir.glob("*"))


def test_too_large_upload_gets_413(admin_client, monkeypatch):
    monkeypatch.setattr(downloads, "max_bytes", lambda: 10)
    monkeypatch.setattr("app.routers.admin_downloads.FORM_OVERHEAD_BYTES", 0)
    response = add_file(admin_client, "task.pdf", PDF)
    assert response.status_code == 413


def test_order_edit_and_delete(admin_client, db, settings):
    for name in ("a.txt", "b.txt", "c.txt"):
        add_file(admin_client, name, name.encode())
    first, second, third = items(db)

    post(
        admin_client,
        "/mtas-admin/downloads/move",
        {"id": third.itid, "direction": "up"},
    )
    assert [row.original_name for row in items(db)] == ["a.txt", "c.txt", "b.txt"]
    post(
        admin_client,
        "/mtas-admin/downloads/move",
        {"id": first.itid, "direction": "up"},
    )
    assert [row.original_name for row in items(db)] == ["a.txt", "c.txt", "b.txt"]

    response = admin_client.post(
        "/mtas-admin/downloads/edit",
        data={
            "csrf_token": csrf_token(admin_client, "/about"),
            "id": str(second.itid),
            "title": "Task B",
            "description": "new version",
        },
        files={"file": ("b2.md", b"# B\n", "text/markdown")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.expire_all()
    changed = db.get(Downloads, second.itid)
    assert (changed.title, changed.original_name, changed.visible) == (
        "Task B",
        "b2.md",
        False,
    )
    assert not (settings.downloads_dir / "b.txt").exists()
    assert (settings.downloads_dir / "b2.md").exists()

    post(admin_client, "/mtas-admin/downloads/delete", {"id": first.itid})
    assert [row.original_name for row in items(db)] == ["c.txt", "b2.md"]
    assert not (settings.downloads_dir / "a.txt").exists()
    actions = {row.action for row in db.query(AdminActions).all()}
    assert {"download_moved", "download_changed", "download_deleted"} <= actions


def test_users_see_the_page_only_when_switched_on(client, db, student):
    login(client)
    assert client.get("/downloads").status_code == 404
    assert 'href="/downloads"' not in client.get("/about").text
    change_ui_visibility_settings(db, "downloads", True)
    assert client.get("/downloads").status_code == 200
    assert 'href="/downloads"' in client.get("/about").text


def test_users_download_the_visible_files(client, db, student):
    exercise = add_exercise(db, "EX2", "ETL", bonus_max_points=5.0)
    db.add(
        ExerciseBonusPoints(user_id=student.itid, exercise_id=exercise.itid, points=3.5)
    )
    db.commit()
    add_user(db, email=ADMIN_EMAIL, pin="9999", number=2)
    login(client, email=ADMIN_EMAIL, pin="9999")
    add_file(client, "task.pdf", PDF, exercise="EX2", title="Task 2")
    hidden = client.post(
        "/mtas-admin/downloads/add",
        data={"csrf_token": csrf_token(client, "/about"), "title": "Solution"},
        files={"file": ("solution.sql", b"SELECT 1;\n", "text/plain")},
        follow_redirects=False,
    )
    assert hidden.status_code == 303
    task, solution = items(db)
    assert not solution.visible
    change_ui_visibility_settings(db, "downloads", True)
    client.cookies.clear()
    login(client)

    page = client.get("/downloads").text
    assert "Task 2" in page and "Solution" not in page
    assert "up to 5.0 points" in page and "your points: 3.5" in page

    response = client.get(f"/downloads/file/{task.itid}")
    assert response.content == PDF
    assert response.headers["content-disposition"].startswith("attachment")
    assert client.get(f"/downloads/file/{solution.itid}").status_code == 404
    assert client.get("/mtas-admin/downloads").status_code == 403
    assert client.get(f"/mtas-admin/downloads/file/{task.itid}").status_code == 403


def test_only_bonus_exercises_can_be_linked(admin_client, db):
    add_exercise(db, "EX1", has_bonus=False)
    response = add_file(admin_client, "a.txt", b"a", exercise="EX1")
    assert response.status_code == 400
    assert "EX1 –" not in admin_client.get("/mtas-admin/downloads").text
