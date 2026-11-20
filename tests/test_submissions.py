import io
import zipfile
from datetime import datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.cli.database import alembic_config
from app.config import ConfigError
from app.database import get_engine, init_engine
from app.models import Exercises, ExerciseSubmissions, SubmissionExtensions
from app.submissions import (
    check_content,
    effective_deadline,
    is_open,
    safe_part,
    split_filename,
)
from app.visibility import change_ui_visibility_settings
from tests.conftest import (
    ADMIN_EMAIL,
    STUDENT_EMAIL,
    add_exercise,
    add_user,
    csrf_token,
    login,
    make_settings,
    post,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
TEXT = "# Report\n\nÄrger mit Umlauten ist kein Problem.\n".encode("utf-8")
MB = 1024 * 1024


def docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


def future(days=7) -> datetime:
    return (datetime.now() + timedelta(days=days)).replace(microsecond=0)


def past(days=1) -> datetime:
    return (datetime.now() - timedelta(days=days)).replace(microsecond=0)


@pytest.fixture
def exercise(db):
    return add_exercise(
        db, "EX01", "Data model", has_submission=True, submission_deadline=future()
    )


@pytest.fixture
def folder(settings, student):
    return settings.submissions_dir / f"{student.itid:04d}_sam.student" / "EX01"


def upload(client, files, code="EX01"):
    return client.post(
        f"/submissions/{code}/upload",
        data={"csrf_token": csrf_token(client, "/about")},
        files=[("files", item) for item in files],
        follow_redirects=False,
    )


def page_text(client, path="/submissions") -> str:
    return client.get(path).text


def active_rows(db):
    db.expire_all()
    return db.query(ExerciseSubmissions).filter_by(deleted=False).all()


# ---- rules ----


def test_safe_names():
    assert split_filename("../../etc/passwd.PDF") == ("passwd", ".pdf")
    assert split_filename("C:\\Users\\me\\My Report (final).docx") == (
        "My_Report_final",
        ".docx",
    )
    # no extension: rejected
    assert split_filename(".md") == ("md", "")
    assert split_filename("???.txt") == ("file", ".txt")
    assert safe_part("..hidden") == "hidden"


def test_deadline_and_extension(db, exercise, student):
    assert is_open(None)
    assert is_open(future())
    assert not is_open(past())
    assert (
        effective_deadline(db, exercise, student.itid) == exercise.submission_deadline
    )
    db.add(
        SubmissionExtensions(
            exercise_id=exercise.itid, user_id=student.itid, deadline=future(30)
        )
    )
    db.commit()
    assert effective_deadline(db, exercise, student.itid) == future(30)


def test_content_checks(tmp_path):
    cases = [
        (".pdf", PDF, True),
        (".pdf", b"not a pdf", False),
        (".docx", docx_bytes(), True),
        (".docx", PDF, False),
        (".md", TEXT, True),
        (".txt", b"binary\x00data", False),
        (".txt", b"\xff\xfe\xfa", False),
    ]
    for ext, content, expected in cases:
        path = tmp_path / f"file{ext}"
        path.write_bytes(content)
        assert check_content(ext, path) is expected, (ext, content)


def test_upload_limit_cannot_be_above_10_mb(tmp_path):
    with pytest.raises(ConfigError, match="SUBMISSION_MAX_FILE_MB"):
        make_settings(tmp_path, SUBMISSION_MAX_FILE_MB="11")
    assert make_settings(tmp_path).submission_max_file_mb == 10


# ---- pages of the student ----


def test_upload_of_all_types(student_client, db, exercise, folder, student):
    response = upload(
        student_client,
        [
            ("report.pdf", PDF, "application/pdf"),
            ("notes.md", TEXT, "text/markdown"),
            ("notes.txt", TEXT, "text/plain"),
            ("report.docx", docx_bytes(), "application/octet-stream"),
        ],
    )
    assert response.status_code == 303
    rows = active_rows(db)
    assert sorted(row.stored_name for row in rows) == [
        "notes.md",
        "notes.txt",
        "report.docx",
        "report.pdf",
    ]
    assert (folder / "report.pdf").read_bytes() == PDF
    pdf = next(row for row in rows if row.stored_name == "report.pdf")
    assert len(pdf.sha256) == 64 and pdf.size_bytes == len(PDF)
    assert pdf.folder == f"{student.itid:04d}_sam.student/EX01"

    text = page_text(student_client)
    assert "Submitted: report.pdf, notes.md, notes.txt, report.docx" in text
    assert f'href="/submissions/file/{pdf.itid}"' in text


def test_same_name_twice_keeps_both(student_client, db, exercise, folder):
    upload(student_client, [("report.pdf", PDF, "application/pdf")])
    upload(student_client, [("report.pdf", PDF, "application/pdf")])
    assert sorted(path.name for path in folder.iterdir()) == [
        "report-2.pdf",
        "report.pdf",
    ]


@pytest.mark.parametrize(
    "name, content, message",
    [
        ("tool.exe", b"MZ", "upload a PDF, TXT, MD or DOCX file"),
        ("fake.pdf", b"<html>", "is not a valid PDF file"),
        ("empty.txt", b"", "is empty"),
        ("big.pdf", b"%PDF-" + b"0" * (10 * MB), "the file is too large"),
    ],
)
def test_wrong_files_are_rejected(
    student_client, db, exercise, folder, name, content, message
):
    upload(student_client, [(name, content, "application/octet-stream")])
    assert active_rows(db) == []
    assert not folder.exists() or list(folder.iterdir()) == []
    assert message in page_text(student_client)


def test_one_upload_has_at_most_10_mb(
    student_client, db, exercise, folder, monkeypatch
):
    # without the check of the Content-Length (e.g. a chunked request)
    monkeypatch.setattr("app.routers.submissions.FORM_OVERHEAD_BYTES", 100 * MB)
    part = b"%PDF-" + b"0" * (4 * MB)
    upload(
        student_client,
        [
            ("a.pdf", part, "application/pdf"),
            ("b.pdf", part, "application/pdf"),
            ("c.pdf", part, "application/pdf"),
        ],
    )
    assert [row.stored_name for row in active_rows(db)] == ["a.pdf", "b.pdf"]
    assert sorted(path.name for path in folder.iterdir()) == ["a.pdf", "b.pdf"]
    assert "c.pdf: the file is too large" in page_text(student_client)


def test_more_than_10_mb_in_one_request_gets_413(student_client, db, exercise):
    part = b"%PDF-" + b"0" * (4 * MB)
    response = upload(
        student_client, [(f"{name}.pdf", part, "application/pdf") for name in "abc"]
    )
    assert response.status_code == 413
    assert active_rows(db) == []


def test_too_large_request_is_rejected_before_reading(
    student_client, db, exercise, monkeypatch
):
    monkeypatch.setattr("app.submissions.max_bytes", lambda: 1000)
    response = upload(
        student_client, [("a.pdf", b"%PDF-" + b"0" * 300_000, "application/pdf")]
    )
    assert response.status_code == 413
    assert "Upload too large" in response.text
    assert active_rows(db) == []


def test_at_most_max_files(student_client, db, exercise):
    upload(student_client, [(f"f{i}.txt", TEXT, "text/plain") for i in range(6)])
    assert len(active_rows(db)) == 5
    text = page_text(student_client)
    assert "at most 5 files" in text
    assert "Delete a file to upload another one" in text


def test_delete_before_deadline(student_client, db, exercise, folder):
    upload(student_client, [("report.pdf", PDF, "application/pdf")])
    row = active_rows(db)[0]
    response = post(
        student_client, "/submissions/EX01/delete", {"submission_id": row.itid}
    )
    assert response.status_code == 303
    db.expire_all()
    row = db.get(ExerciseSubmissions, row.itid)
    assert row.deleted and row.deleted_at
    assert not (folder / "report.pdf").exists()
    assert "Deleted: report.pdf" in page_text(student_client)


def test_after_deadline_no_upload_and_no_delete(student_client, db, exercise, folder):
    upload(student_client, [("report.pdf", PDF, "application/pdf")])
    row = active_rows(db)[0]
    exercise.submission_deadline = past()
    db.commit()

    upload(student_client, [("late.pdf", PDF, "application/pdf")])
    post(student_client, "/submissions/EX01/delete", {"submission_id": row.itid})
    assert [r.stored_name for r in active_rows(db)] == ["report.pdf"]
    assert (folder / "report.pdf").exists()
    text = page_text(student_client)
    assert "The deadline has passed" in text
    assert 'action="/submissions/EX01/upload"' not in text


def test_extension_opens_the_upload_again(student_client, db, exercise, student):
    exercise.submission_deadline = past()
    db.add(
        SubmissionExtensions(
            exercise_id=exercise.itid, user_id=student.itid, deadline=future()
        )
    )
    db.commit()
    upload(student_client, [("report.pdf", PDF, "application/pdf")])
    assert len(active_rows(db)) == 1
    assert "your personal deadline" in page_text(student_client)


def test_files_of_others_are_not_reachable(client, db, exercise):
    other = add_user(db, email="kim.lee@uni.example", pin="5555", number=3)
    add_user(db)
    login(client, email="kim.lee@uni.example", pin="5555")
    upload(client, [("secret.pdf", PDF, "application/pdf")])
    row = active_rows(db)[0]
    assert row.user_id == other.itid
    assert client.get(f"/submissions/file/{row.itid}").status_code == 200

    client.cookies.clear()
    login(client)
    assert client.get(f"/submissions/file/{row.itid}").status_code == 404
    post(client, "/submissions/EX01/delete", {"submission_id": row.itid})
    assert len(active_rows(db)) == 1


def test_download_is_an_attachment(student_client, db, exercise):
    upload(student_client, [("notes.md", TEXT, "text/markdown")])
    row = active_rows(db)[0]
    response = student_client.get(f"/submissions/file/{row.itid}")
    assert response.content == TEXT
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_exercise_without_submissions_is_not_open(student_client, db, exercise):
    add_exercise(db, "EX02", "Hidden", order=2, has_submission=True, visible=False)
    add_exercise(db, "EX03", "No files", order=3, has_submission=False)
    for code in ("EX02", "EX03", "NOPE"):
        response = upload(
            student_client, [("a.pdf", PDF, "application/pdf")], code=code
        )
        assert response.status_code == 404
    text = page_text(student_client)
    assert "Data model" in text and "Hidden" not in text and "No files" not in text


def test_hidden_menu_entry_closes_the_pages(student_client, db, exercise):
    assert 'href="/submissions"' in page_text(student_client, "/services")
    change_ui_visibility_settings(db, "submissions", False)
    assert student_client.get("/submissions").status_code == 404
    assert 'href="/submissions"' not in page_text(student_client, "/services")


def test_login_is_needed(client, exercise):
    response = client.get("/submissions", follow_redirects=False)
    assert response.headers["location"] == "/login"


def test_confirmation_email_only_when_switched_on(
    student_client, db, exercise, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        "app.submissions.send_email",
        lambda to, subject, content, settings: sent.append((to, subject, content))
        or True,
    )
    upload(student_client, [("a.pdf", PDF, "application/pdf")])
    assert sent == []

    exercise.submission_email = True
    db.commit()
    upload(student_client, [("b.pdf", PDF, "application/pdf")])
    row = active_rows(db)[-1]
    post(student_client, "/submissions/EX01/delete", {"submission_id": row.itid})
    assert [(to, subject) for to, subject, _ in sent] == [
        (STUDENT_EMAIL, "Submission received: EX01"),
        (STUDENT_EMAIL, "Submission deleted: EX01"),
    ]
    assert row.sha256 in sent[0][2]


def test_too_large_page_of_nginx(student_client):
    response = student_client.get("/submissions/too-large", follow_redirects=False)
    assert response.headers["location"] == "/submissions"
    assert "at most 10 MB" in page_text(student_client)


# ---- admin pages ----


def test_admin_pages_need_admin(student_client, exercise):
    for path in (
        "/mtas-admin/exercises",
        "/mtas-admin/submissions",
        "/mtas-admin/submissions/zip/EX01",
        "/mtas-admin/exercises/export",
    ):
        assert student_client.get(path).status_code == 403


def test_admin_creates_and_edits_an_exercise(admin_client, db):
    response = post(
        admin_client,
        "/mtas-admin/exercises/edit",
        {
            "code": "EX09",
            "name": "Report",
            "submission_deadline": "2030-01-31T23:59",
            "visible": "on",
            "has_submission": "on",
            "submission_email": "on",
        },
    )
    assert response.status_code == 303
    exercise = db.query(Exercises).filter_by(code="EX09").one()
    assert exercise.submission_deadline == datetime(2030, 1, 31, 23, 59)
    assert exercise.has_submission and exercise.submission_email
    assert not exercise.has_review

    post(
        admin_client,
        "/mtas-admin/exercises/edit",
        {"original_code": "EX09", "code": "OTHER", "name": "Report 2"},
    )
    db.expire_all()
    exercise = db.query(Exercises).filter_by(code="EX09").one()
    assert exercise.name == "Report 2"
    assert exercise.submission_deadline is None and not exercise.has_submission
    assert "Report 2" in page_text(admin_client, "/mtas-admin/exercises")


def test_admin_downloads_the_exercises_as_csv(admin_client, exercise):
    assert 'href="/mtas-admin/exercises/export"' in page_text(
        admin_client, "/mtas-admin/exercises"
    )
    response = admin_client.get("/mtas-admin/exercises/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="initial_exercises-'
    )
    header, row = response.text.splitlines()
    assert header.startswith("code;name;description;")
    assert row.startswith("EX01;Data model;")


@pytest.mark.parametrize(
    "data, message",
    [
        ({"code": "bad code", "name": "x"}, "Enter a code"),
        ({"code": "EX01", "name": "x"}, "already exists"),
        ({"code": "EX05", "name": ""}, "Enter a name"),
        ({"code": "EX05", "name": "x", "year": "abc"}, "as numbers"),
        ({"code": "EX05", "name": "x", "submission_deadline": "soon"}, "deadline"),
    ],
)
def test_admin_exercise_form_checks_the_values(admin_client, exercise, data, message):
    response = post(admin_client, "/mtas-admin/exercises/edit", data)
    assert response.status_code == 400
    assert message in response.text


def test_admin_sees_files_downloads_and_zips(client, db, exercise, settings):
    student = add_user(db)
    add_user(db, email=ADMIN_EMAIL, pin="9999", number=2)
    login(client)
    upload(client, [("report.pdf", PDF, "application/pdf")])
    row = active_rows(db)[0]
    client.cookies.clear()
    login(client, email=ADMIN_EMAIL, pin="9999")

    overview = page_text(client, "/mtas-admin/submissions")
    assert "1 of 2" in overview
    assert f"/mtas-admin/submissions/detail?user={student.itid}&amp;exercise=EX01" in (
        overview
    )
    detail = page_text(
        client, f"/mtas-admin/submissions/detail?user={student.itid}&exercise=EX01"
    )
    assert "report.pdf" in detail and row.sha256[:12] in detail

    assert client.get(f"/mtas-admin/submissions/file/{row.itid}").content == PDF

    response = client.get("/mtas-admin/submissions/zip/EX01")
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == [f"EX01/{student.itid:04d}_sam.student/report.pdf"]
        assert archive.read(archive.namelist()[0]) == PDF


def test_admin_zip_without_files(admin_client, exercise):
    response = admin_client.get(
        "/mtas-admin/submissions/zip/EX01", follow_redirects=False
    )
    assert response.status_code == 303
    assert "There are no files for EX01" in page_text(
        admin_client, "/mtas-admin/submissions"
    )


def test_admin_sets_and_removes_an_extension(admin_client, db, exercise):
    student = add_user(db)
    data = {"user": student.itid, "exercise": "EX01"}
    post(
        admin_client,
        "/mtas-admin/submissions/extension",
        {**data, "deadline": "2031-02-01T12:00", "note": "ill"},
    )
    extension = db.query(SubmissionExtensions).one()
    assert (extension.deadline, extension.note) == (datetime(2031, 2, 1, 12), "ill")

    post(admin_client, "/mtas-admin/submissions/extension", {**data, "remove": "true"})
    db.expire_all()
    assert db.query(SubmissionExtensions).count() == 0


def test_admin_deletes_after_the_deadline(client, db, exercise, folder):
    add_user(db)
    add_user(db, email=ADMIN_EMAIL, pin="9999", number=2)
    login(client)
    upload(client, [("report.pdf", PDF, "application/pdf")])
    row = active_rows(db)[0]
    exercise.submission_deadline = past()
    db.commit()
    client.cookies.clear()
    login(client, email=ADMIN_EMAIL, pin="9999")
    post(client, "/mtas-admin/submissions/delete", {"submission_id": row.itid})
    assert active_rows(db) == []
    assert not (folder / "report.pdf").exists()


# ---- migration ----


def test_migration_keeps_the_exercises(settings):
    init_engine(settings.database_url)
    command.upgrade(alembic_config(), "e3b7c1d9a2f4")
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "INSERT INTO exercises (code, name, visible, has_review, has_bonus) "
                "VALUES ('OLD1', 'Old exercise', 1, 1, 0)"
            )
        )
    command.upgrade(alembic_config(), "head")
    tables = inspect(get_engine()).get_table_names()
    assert {"exercise_submissions", "submission_extensions"} <= set(tables)
    with get_engine().connect() as connection:
        row = connection.execute(
            text("SELECT name, has_submission, submission_email FROM exercises")
        ).one()
    assert tuple(row) == ("Old exercise", 0, 0)

    command.downgrade(alembic_config(), "e3b7c1d9a2f4")
    assert "exercise_submissions" not in inspect(get_engine()).get_table_names()
