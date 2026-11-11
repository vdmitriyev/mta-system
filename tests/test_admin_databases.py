"""Admin pages of PostgreSQL and pgAdmin 4"""

import pytest

from app.models import PGAdmin4Service, PostgreSQLService
from app.routers import admin as admin_router
from app.services import basic_auth, postgresql
from tests.conftest import STUDENT_EMAIL, add_postgresql, add_user, post
from tests.test_databases_for_students import FakeMate, down, fake_connect


@pytest.fixture
def mate(settings, monkeypatch):
    fake = FakeMate()
    fake.databases = ["bicourse_db_01", "db_demo"]
    monkeypatch.setattr(postgresql, "mate", lambda: fake)
    monkeypatch.setattr(postgresql, "connect", fake_connect())
    return fake


def test_postgresql_page_shows_the_server_and_the_databases(
    admin_client, db, student, mate
):
    add_postgresql(db, student)
    other = add_user(db, email="other@uni.example", number=3)
    add_postgresql(db, other, number=3)

    text = admin_client.get("/mtas-admin/services/postgresql").text
    assert "The database server is reachable" in text
    assert "<code>localhost:5432</code>" in text and "PostgreSQL 15.8" in text
    assert "Demo database <code>db_demo</code>" in text
    assert '<span class="badge success">exists</span>' in text
    # the database of the other user is missing on the server
    assert '<span class="badge danger">missing</span>' in text
    # one database exists (set password), one is missing (create)
    assert text.count('action="/mtas-admin/services/postgresql/password"') == 1
    assert text.count('action="/mtas-admin/services/postgresql/create"') == 2


def test_postgresql_page_without_server(admin_client, student, settings, monkeypatch):
    monkeypatch.setattr(postgresql, "connect", fake_connect(down()))
    text = admin_client.get("/mtas-admin/services/postgresql").text
    assert "The database server is not reachable" in text
    assert "connection refused" in text
    assert "disabled" in text


def test_postgresql_access_check(admin_client, db, student, mate, monkeypatch):
    add_postgresql(db, student)
    seen = []
    monkeypatch.setattr(
        postgresql,
        "check_user_access",
        lambda *args: seen.append(args) or postgresql.ACCESS_LOGIN_FAILED,
    )
    text = admin_client.get("/mtas-admin/services/postgresql").text
    assert seen == [] and "LOGIN FAILED" not in text

    text = admin_client.get("/mtas-admin/services/postgresql?check=access").text
    assert seen == [("bicourse_db_01", "bicourse_user_01", "pg-secret-11")]
    assert "LOGIN FAILED" in text
    assert "NO SERVICE" in text  # the admin has no database


def test_create_database_for_a_user_without_account(admin_client, db, student, mate):
    response = post(
        admin_client,
        "/mtas-admin/services/postgresql/create",
        {"user_id": student.itid},
    )
    assert response.headers["location"] == "/mtas-admin/services/postgresql"
    entry = db.query(PostgreSQLService).one()
    assert (entry.postgresql_db, entry.postgresql_user, entry.created) == (
        "bicourse_db_01",
        "bicourse_user_01",
        True,
    )
    assert mate.calls[-2] == (
        "create_db",
        "bicourse_db_01",
        "bicourse_user_01",
        entry.postgresql_password,
    )
    text = admin_client.get("/mtas-admin/services/postgresql").text
    assert "The database bicourse_db_01 was created for" in text


def test_missing_database_is_created_again_with_the_stored_login(
    admin_client, db, student, mate
):
    entry = add_postgresql(db, student)
    mate.databases = []
    post(
        admin_client,
        "/mtas-admin/services/postgresql/create",
        {"user_id": student.itid},
    )
    assert ("create_db", "bicourse_db_01", "bicourse_user_01", "pg-secret-11") in (
        mate.calls
    )
    db.refresh(entry)
    assert entry.created is True
    assert db.query(PostgreSQLService).count() == 1


def test_existing_database_is_not_created_again(admin_client, db, student, mate):
    add_postgresql(db, student)
    post(
        admin_client,
        "/mtas-admin/services/postgresql/create",
        {"user_id": student.itid},
    )
    text = admin_client.get("/mtas-admin/services/postgresql").text
    assert "already exists" in text
    assert not any(call[0] == "create_db" for call in mate.calls)


def test_create_database_errors_are_shown(admin_client, db, student, mate):
    mate.fail["list_dbs"] = down()
    post(
        admin_client,
        "/mtas-admin/services/postgresql/create",
        {"user_id": student.itid},
    )
    assert (
        "server is not reachable"
        in admin_client.get("/mtas-admin/services/postgresql").text
    )


def test_set_password(admin_client, db, student, mate):
    add_postgresql(db, student)
    post(
        admin_client,
        "/mtas-admin/services/postgresql/password",
        {"user_id": student.itid},
    )
    assert mate.calls[-1] == ("set_user_password", "bicourse_user_01", "pg-secret-11")
    text = admin_client.get("/mtas-admin/services/postgresql").text
    assert f"on the services page of {STUDENT_EMAIL}" in text


def test_set_password_without_account(admin_client, db, student, mate):
    post(
        admin_client,
        "/mtas-admin/services/postgresql/password",
        {"user_id": student.itid},
    )
    assert (
        "has no PostgreSQL account"
        in admin_client.get("/mtas-admin/services/postgresql").text
    )


# ---------- pgAdmin 4 ----------


def add_pgadmin4(db, user, login="common_user_01", password="pa-pw"):
    entry = PGAdmin4Service(
        user_id=user.itid, pgadmin4_user=login, pgadmin4_password=password, created=True
    )
    db.add(entry)
    db.commit()
    return entry


def test_pgadmin4_page_shows_the_login_file(admin_client, db, student):
    add_pgadmin4(db, student)
    text = admin_client.get("/mtas-admin/services/pgadmin4").text
    assert "0 logins" in text
    assert "MISSING" in text

    basic_auth.set_basic_auth_user(
        "common_user_01", "other", basic_auth.common_auth_file()
    )
    text = admin_client.get("/mtas-admin/services/pgadmin4").text
    assert "1 login" in text and "WRONG PASSWORD" in text


def test_write_pgadmin4_login(admin_client, db, student):
    add_pgadmin4(db, student)
    post(admin_client, "/mtas-admin/services/pgadmin4/login", {"user_id": student.itid})
    assert (
        basic_auth.login_state("common_user_01", "pa-pw", basic_auth.common_auth_file())
        == basic_auth.LOGIN_OK
    )
    text = admin_client.get("/mtas-admin/services/pgadmin4").text
    assert '<span class="badge success">OK</span>' in text


def test_create_pgadmin4_account_with_the_postgresql_password(
    admin_client, db, student
):
    add_postgresql(db, student)
    post(admin_client, "/mtas-admin/services/pgadmin4/login", {"user_id": student.itid})
    entry = db.query(PGAdmin4Service).one()
    assert (entry.pgadmin4_user, entry.pgadmin4_password) == (
        "common_user_01",
        "pg-secret-11",
    )
    assert (
        basic_auth.login_state(
            "common_user_01", "pg-secret-11", basic_auth.common_auth_file()
        )
        == basic_auth.LOGIN_OK
    )


def test_pgadmin4_access_check(admin_client, db, student, monkeypatch):
    add_pgadmin4(db, student)
    seen = []
    monkeypatch.setattr(
        "app.routers.admin_databases.check_basic_auth",
        lambda url, login, password: seen.append((url, login, password)) or "401",
    )
    text = admin_client.get("/mtas-admin/services/pgadmin4?check=access").text
    assert seen == [("https://mtas.example.org/pgadmin4", "common_user_01", "pa-pw")]
    assert '<span class="badge danger">401</span>' in text


def test_login_state_helpers(tmp_path):
    auth_file = str(tmp_path / "logins.htpasswd")
    assert basic_auth.login_state("u", "p", auth_file) == basic_auth.LOGIN_MISSING
    assert basic_auth.count_logins(auth_file) == 0
    basic_auth.set_basic_auth_user("u", "p", auth_file)
    assert basic_auth.login_state("u", "p", auth_file) == basic_auth.LOGIN_OK
    assert basic_auth.login_state("u", "x", auth_file) == (
        basic_auth.LOGIN_WRONG_PASSWORD
    )
    assert basic_auth.login_state("v", "p", auth_file) == basic_auth.LOGIN_MISSING
    assert basic_auth.count_logins(auth_file) == 1


# ---------- menu, rights ----------


@pytest.mark.parametrize("service", ["postgresql", "pgadmin4"])
def test_pages_are_in_the_services_menu(admin_client, mate, service):
    text = admin_client.get(f"/mtas-admin/services/{service}").text
    menu = text[text.index("<details") : text.index("</details>")]
    assert '<summary aria-current="page">Services' in menu
    assert f'href="/mtas-admin/services/{service}" aria-current="page"' in menu


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/mtas-admin/services/postgresql"),
        ("get", "/mtas-admin/services/pgadmin4"),
        ("post", "/mtas-admin/services/postgresql/create"),
        ("post", "/mtas-admin/services/postgresql/password"),
        ("post", "/mtas-admin/services/pgadmin4/login"),
    ],
)
def test_students_have_no_access(student_client, method, path):
    response = getattr(student_client, method)(path, follow_redirects=False)
    assert response.status_code in (303, 403, 404)


def test_metabase_page_still_works(admin_client, docker):
    assert admin_client.get("/mtas-admin/services/metabase").status_code == 200
    assert admin_router.MANAGED_SERVICES == {
        "metabase": "Metabase",
        "openrefine": "OpenRefine",
    }
