import pytest

from app import provisioning
from app.models import (
    MariaDBService,
    MetabaseService,
    SupersetService,
    WordpressService,
)
from app.provisioning import email_to_tokens
from app.service_settings import DEPRECATED_SERVICES, SERVICE_KEYS
from tests.conftest import add_user, force_on, switch_on

ACTIVE = [key for key in SERVICE_KEYS if key not in DEPRECATED_SERVICES]


def test_email_to_tokens():
    assert email_to_tokens("jane.doe@x.org") == ["jane", "doe"]
    assert email_to_tokens("jane@x.org") == ["jane", "Unknown"]


def test_services_that_are_switched_off_create_nothing(db, settings, docker):
    user = add_user(db)
    assert not provisioning.postgresql_service_user(db, user.itid, "d", "u", "p")
    assert not provisioning.pgadmin4_user(db, user.itid, "u", "p")
    assert not provisioning.jupyterhub_user(db, user.itid, "u", "p")
    assert not provisioning.metabase_user(db, user.itid, "a.b@x.org", "p", 3001)
    assert not provisioning.openrefine_user(db, user.itid, "u", "p", 4001)
    assert not provisioning.mariadb_user(db, user.itid, "d", "u", "p")
    assert not provisioning.wordpress_user(db, user.itid, "u", "e@x.org", "p", 7001)
    assert not provisioning.nifi_user(db, user.itid, "u", "p", 6001)
    assert not provisioning.superset_user(db, user.itid, "u", "p", "e@x.org")
    assert docker.containers.runs == []
    from app.users import get_user_services

    assert get_user_services(db, user.itid) == {}


def test_metabase_account(db, use_settings, monkeypatch):
    switch_on(db, *ACTIVE)
    user = add_user(db)
    seen = []
    monkeypatch.setattr(
        "app.provisioning.metabase_api.create_user_and_docker_mb",
        lambda data, port: seen.append((data, port)) or True,
    )

    assert (
        provisioning.metabase_user(db, user.itid, "jane.doe@x.org", "pw", 3001) is True
    )
    data, port = seen[0]
    assert (data.fname, data.lname, port) == ("Jane", "Doe", 3001)
    entry = db.query(MetabaseService).one()
    assert (entry.metabase_login, entry.metabase_docker_port, entry.created) == (
        "jane.doe@x.org",
        3001,
        True,
    )


def test_failed_creation_is_stored_as_not_created(db, use_settings, monkeypatch):
    switch_on(db, *ACTIVE)
    user = add_user(db)
    monkeypatch.setattr(
        "app.provisioning.metabase_api.create_user_and_docker_mb", lambda *_a: False
    )
    assert (
        provisioning.metabase_user(db, user.itid, "jane.doe@x.org", "pw", 3001) is False
    )
    assert db.query(MetabaseService).one().created is False


@pytest.mark.parametrize("service", ["metabase", "openrefine"])
def test_force_create_ignores_the_switch(db, settings, docker, monkeypatch, service):
    user = add_user(db)
    monkeypatch.setattr(
        "app.provisioning.metabase_api.create_user_and_docker_mb", lambda *_a: True
    )
    if service == "metabase":
        result = provisioning.metabase_user(
            db, user.itid, "a.b@x.org", "pw", 3001, force_create=True
        )
    else:
        result = provisioning.openrefine_user(
            db, user.itid, "common_user_01", "pw", 4001, force_create=True
        )
    assert result is True


def test_mariadb_and_wordpress(db, use_settings, monkeypatch):
    use_settings(MARIADB_DB_HOST="mariadb")
    switch_on(db, *ACTIVE)
    user = add_user(db)
    seen = []
    monkeypatch.setattr("app.provisioning.mariadb.create_mariadb_db", lambda *a: True)
    monkeypatch.setattr(
        "app.provisioning.wordpress_api.create_user_and_docker_wordpress",
        lambda data, port: seen.append((data, port)) or True,
    )

    assert provisioning.mariadb_user(db, user.itid, "wp_db", "wp_user", "dbpw") is True
    assert provisioning.wordpress_user(
        db, user.itid, "wordpress_user_01", "e@x.org", "pw", 7001
    )

    data, port = seen[0]
    assert port == 7001
    assert (
        data.databaseHost,
        data.databaseName,
        data.databaseUser,
        data.databasePassword,
    ) == (
        "mariadb",
        "wp_db",
        "wp_user",
        "dbpw",
    )
    assert data.wordpressBaseURL == "http://mtas.example.org/wordpress/"
    assert db.query(MariaDBService).one().created is True
    assert db.query(WordpressService).one().wordpress_docker_port == 7001


def test_wordpress_needs_the_mariadb_database_of_the_user(db, use_settings):
    switch_on(db, *ACTIVE)
    user = add_user(db)
    assert (
        provisioning.wordpress_user(db, user.itid, "u", "e@x.org", "pw", 7001) is False
    )
    assert db.query(WordpressService).count() == 0


@pytest.mark.parametrize("service", sorted(DEPRECATED_SERVICES))
def test_deprecated_services_create_nothing(db, docker, monkeypatch, service):
    # switched on before the deprecation: still no account
    force_on(db, service)
    user = add_user(db)
    monkeypatch.setattr(
        "app.provisioning.superset_api.SupersetAPIClient", pytest.fail, raising=True
    )
    create = {
        "superset": lambda: provisioning.superset_user(
            db, user.itid, "login", "pw", "e@x.org"
        ),
        "nifi": lambda: provisioning.nifi_user(db, user.itid, "u", "pw", 6001),
        "jupyterhub": lambda: provisioning.jupyterhub_user(db, user.itid, "u", "pw"),
    }[service]
    assert create() is False
    assert db.query(SupersetService).count() == 0
    assert docker.containers.runs == []


def test_wordpress_reaches_mariadb_by_its_own_address(db, use_settings, monkeypatch):
    use_settings(MARIADB_DB_HOST="127.0.0.1", WORDPRESS_DB_HOST="mariadb")
    switch_on(db, *ACTIVE)
    user = add_user(db)
    seen = []
    monkeypatch.setattr("app.provisioning.mariadb.create_mariadb_db", lambda *a: True)
    monkeypatch.setattr(
        "app.provisioning.wordpress_api.create_user_and_docker_wordpress",
        lambda data, port: seen.append(data) or True,
    )
    provisioning.mariadb_user(db, user.itid, "wp_db", "wp_user", "dbpw")
    provisioning.wordpress_user(
        db, user.itid, "wordpress_user_01", "e@x.org", "pw", 7001
    )
    assert seen[0].databaseHost == "mariadb"
