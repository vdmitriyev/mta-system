import pytest

from app import users
from app.config import set_settings
from app.models import (
    JupyterHubService,
    MetabaseService,
    PostgreSQLService,
    Users,
)
from app.tasks import TaskError
from app.users import (
    access_url,
    assign_available_account,
    container_name,
    course_users,
    email_to_name,
    find_user_by_email,
    find_user_by_hash,
    generate_accounts_task,
    generate_internal_email,
    get_user_services,
    is_admin,
    is_email_in_allowed_fqdn_list,
    next_account_number,
    postgresql_uri,
    register_new_user,
    register_user_task,
    validate_credentials,
)
from tests.conftest import (
    ADMIN_EMAIL,
    add_postgresql,
    add_user,
    make_settings,
    switch_on,
)


def test_email_to_name():
    assert email_to_name("jane.doe@uni.example") == "Jane Doe"
    assert email_to_name("jane@uni.example") == "Jane Unknown"


def test_generate_internal_email():
    assert (
        generate_internal_email("u_01", "mtas.example.org") == "u_01@mtas.example.org"
    )
    assert generate_internal_email("u_01", "localhost") == "u_01@localhost.loc"


@pytest.mark.parametrize(
    "email,allowed,expected",
    [
        ("a@uni.example", ["uni.example"], True),
        ("a@other.org", ["uni.example"], False),
        ("a@other.org", [], True),
        ("no-at-sign", [], False),
        ("A@UNI.Example", ["uni.example"], True),
        ("a@uni.example", ["@Uni.Example"], True),
        ("a@sub.uni.example", ["uni.example"], False),
    ],
)
def test_allowed_email_domains(email, allowed, expected):
    assert is_email_in_allowed_fqdn_list(email, allowed) is expected


def test_find_user(db, student):
    assert find_user_by_hash(db, student.url_hash).itid == student.itid
    assert find_user_by_hash(db, "unknown") is None
    assert find_user_by_hash(db, None) is None
    assert find_user_by_email(db, student.email).itid == student.itid

    student.deleted = True
    db.commit()
    assert find_user_by_hash(db, student.url_hash) is None
    assert find_user_by_email(db, student.email) is None


def test_validate_credentials(db, student):
    assert (
        validate_credentials(db, student.url_hash, student.pin_hash).itid
        == student.itid
    )
    assert validate_credentials(db, student.url_hash, users.pin_hash("0000")) is None
    assert validate_credentials(db, student.url_hash, "") is None

    student.active = False
    db.commit()
    assert validate_credentials(db, student.url_hash, student.pin_hash) is None


def test_is_admin(db, student, admin):
    assert is_admin(admin)
    assert not is_admin(student)
    assert not is_admin(None)


def test_course_users_are_of_this_course_and_sorted(db, student, admin):
    other = add_user(db, email="zoe@uni.example", number=3)
    other.course_code = "OLD"
    db.commit()
    assert [user.email for user in course_users(db)] == [ADMIN_EMAIL, student.email]


def test_access_url(settings, student):
    url = access_url(student)
    assert url.startswith("https://mtas.example.org/login?uHash=")
    assert student.url_hash in url and student.pin_hash in url


def test_user_services_use_the_newest_row_that_is_not_deleted(db, student):
    assert get_user_services(db, student.itid) == {}
    for port, deleted in ((3001, True), (3002, False), (3003, True)):
        db.add(
            MetabaseService(
                user_id=student.itid,
                metabase_login="x",
                metabase_password="y",
                metabase_docker_port=port,
                deleted=deleted,
            )
        )
    db.commit()
    add_postgresql(db, student)

    services = get_user_services(db, student.itid)
    assert set(services) == {"metabase", "postgresql"}
    assert container_name("metabase", services["metabase"]) == "metabase-3002"
    assert container_name("postgresql", services["postgresql"]) is None


def test_postgresql_uri(db, student):
    entry = add_postgresql(db, student)
    assert (
        postgresql_uri(entry)
        == "postgresql+psycopg2://bicourse_user_01:pg-secret-11@localhost:5432/bicourse_db_01"
    )


def test_next_account_number_without_postgresql(db):
    assert next_account_number(db) == 1
    add_user(db)
    assert next_account_number(db) == 2


def test_next_account_number_comes_from_postgresql(db, tmp_path, monkeypatch):
    switch_on(db, "postgresql")
    monkeypatch.setattr("app.users.postgresql.next_database_number", lambda: 7)
    assert next_account_number(db) == 7

    monkeypatch.setattr("app.users.postgresql.next_database_number", lambda: None)
    with pytest.raises(TaskError, match="not available"):
        next_account_number(db)


def test_register_new_user_without_services(db, settings):
    user = register_new_user(db, "new.user@uni.example")
    assert user.email == "new.user@uni.example"
    assert user.internal_email == "bicourse_user_01@mtas.example.org"
    assert user.course_code == settings.course_security_code
    assert user.is_user_assigned is True
    assert len(user.pin) == 4
    assert validate_credentials(db, user.url_hash, users.pin_hash(user.pin))
    assert get_user_services(db, user.itid) == {}


def test_register_new_user_creates_the_services(db, tmp_path, monkeypatch, docker):
    switch_on(db, "postgresql", "pgadmin4", "jupyterhub", "openrefine", "nifi")
    created = []
    monkeypatch.setattr("app.users.postgresql.next_database_number", lambda: 12)
    monkeypatch.setattr(
        "app.provisioning.postgresql.create_postgresql_db",
        lambda *args: created.append(args) or True,
    )

    user = register_new_user(db, "new.user@uni.example")
    services = get_user_services(db, user.itid)

    assert set(services) == {
        "postgresql",
        "pgadmin4",
        "jupyterhub",
        "openrefine",
        "nifi",
    }
    password = services["postgresql"].postgresql_password
    assert created == [("bicourse_db_12", "bicourse_user_12", password)]
    assert services["pgadmin4"].pgadmin4_user == "common_user_12"
    assert services["jupyterhub"].jupyterhub_user == "jh_user_12"
    assert services["openrefine"].openrefine_docker_port == 4012
    assert services["nifi"].nifi_docker_port == 6012
    assert services["nifi"].nifi_password == password
    assert {run["name"] for run in docker.containers.runs} == {
        "openrefine-4012",
        "nifi-6012",
    }
    assert (tmp_path / "htpasswd" / "4012.htpasswd").exists()
    assert (tmp_path / "htpasswd" / "common-basic-auth.db").exists()


def test_a_broken_service_does_not_stop_the_registration(db, tmp_path, monkeypatch):
    switch_on(db, "postgresql", "jupyterhub")

    def broken(*_args):
        raise RuntimeError("PostgreSQL is down")

    monkeypatch.setattr("app.users.postgresql.next_database_number", lambda: 3)
    monkeypatch.setattr("app.provisioning.postgresql.create_postgresql_db", broken)

    user = register_new_user(db, "new.user@uni.example")
    assert db.query(PostgreSQLService).count() == 0
    assert db.query(JupyterHubService).filter_by(user_id=user.itid).count() == 1


def test_assign_available_account(db):
    assert assign_available_account(db, "new.user@uni.example") is None

    prepared = add_user(db, email="tmp.generated0@localhost.lc", assigned=False)
    old_pin_hash = prepared.pin_hash
    user = assign_available_account(db, "new.user@uni.example")

    assert user.itid == prepared.itid
    assert user.email == "new.user@uni.example"
    assert user.is_user_assigned is True
    assert user.url_hash == users.email_hash("new.user@uni.example")
    assert user.pin_hash == old_pin_hash
    assert assign_available_account(db, "second@uni.example") is None


def test_register_task_for_a_new_user(db, no_email):
    message = register_user_task(db, "new.user@uni.example")
    assert "complete" in message
    user = find_user_by_email(db, "new.user@uni.example")
    assert no_email[0]["to"] == "new.user@uni.example"
    assert user.pin in no_email[0]["content"]
    assert access_url(user) in no_email[0]["content"]


def test_register_task_uses_a_prepared_account(db, no_email):
    prepared = add_user(db, email="tmp.generated0@localhost.lc", assigned=False)
    register_user_task(db, "new.user@uni.example")
    assert db.query(Users).count() == 1
    assert find_user_by_email(db, "new.user@uni.example").itid == prepared.itid
    assert len(no_email) == 1


def test_register_task_for_a_known_user_sends_the_login_again(db, student, no_email):
    message = register_user_task(db, student.email)
    assert "already registered" in message
    assert db.query(Users).count() == 1
    assert no_email[0]["to"] == student.email


def test_register_task_reports_an_email_that_was_not_sent(db, monkeypatch):
    monkeypatch.setattr("app.users.send_email", lambda **_kwargs: False)
    with pytest.raises(TaskError, match="could not send the e-mail"):
        register_user_task(db, "new.user@uni.example")
    assert find_user_by_email(db, "new.user@uni.example") is not None


def test_generate_accounts_task(db, monkeypatch):
    pauses = []
    monkeypatch.setattr("app.users.time.sleep", pauses.append)
    assert generate_accounts_task(db, 3) == "Prepared accounts: 3"
    prepared = db.query(Users).all()
    assert len(prepared) == 3
    assert all(not user.is_user_assigned for user in prepared)
    assert len({user.internal_email for user in prepared}) == 3
    assert len(pauses) == 2


def test_login_link_is_logged_in_development_only(db, student, caplog, tmp_path):
    with caplog.at_level("INFO"):
        users.send_access_email(student)
    assert "Login link" in caplog.text

    caplog.clear()
    set_settings(make_settings(tmp_path, TARGET_SERVER="production"))
    with caplog.at_level("INFO"):
        users.send_access_email(student)
    assert "Login link" not in caplog.text
