"""PostgreSQL (through dbsetupmate) and MariaDB services for the students.

The tests replace the database servers. The SQL of dbsetupmate runs against a real
PostgreSQL in the Docker test copy (task testenv:deploy).
"""

from contextlib import contextmanager

import pytest
from dbsetupmate import (
    DatabaseAlreadyExistsException,
    DatabaseNames,
    DBConnectionException,
    DBUserAlreadyExistsException,
    DBUserNotExistsException,
    ManagedDatabase,
)

from app.services import mariadb, postgresql

# ----- PostgreSQL -----


class FakeMate:
    """Records the calls of the app. Set "fail" to raise an error in a method."""

    def __init__(self):
        self.calls = []
        self.fail = {}
        self.databases = ["bicourse_db_01", "bicourse_db_04"]

    def _call(self, name, *args):
        self.calls.append((name, *args))
        if name in self.fail:
            raise self.fail[name]

    def create_db(self, db_name, db_user, password):
        self._call("create_db", db_name, db_user, password)

    def grant_shared_access(self, role):
        self._call("grant_shared_access", role)

    def show_next_db_name(self):
        self._call("show_next_db_name")
        return DatabaseNames("bicourse_db_05", "bicourse_user_05", 5)

    def list_dbs(self):
        self._call("list_dbs")
        return [ManagedDatabase(name, name) for name in self.databases]

    def database_exists(self, name):
        self._call("database_exists", name)
        return name in self.databases

    def set_user_password(self, user, password):
        self._call("set_user_password", user, password)
        return user

    def grant_public_schema_rights(self, db_name, db_user):
        self._call("grant_public_schema_rights", db_name, db_user)

    def create_shared_db(self):
        self._call("create_shared_db")

    def harden_shared_schema(self):
        self._call("harden_shared_schema")

    def create_shared_user_readonly(self, user, password):
        self._call("create_shared_user_readonly", user, password)


@pytest.fixture
def mate(settings, monkeypatch):
    fake = FakeMate()
    monkeypatch.setattr(postgresql, "mate", lambda: fake)
    return fake


def down():
    return DBConnectionException("Could not connect: connection refused")


def test_config_comes_from_the_settings(use_settings):
    use_settings(
        POSTGRESQL_DB_HOST="pg",
        POSTGRESQL_DB_HOST_PORT="5433",
        POSTGRESQL_ADMIN_PASSWORD="admin-pw",
        POSTGRESQL_DEMO_DB="demo",
        POSTGRESQL_DEMO_USER="demo_owner",
    )
    cfg = postgresql.config()
    assert (cfg.host, cfg.port, cfg.admin_password) == ("pg", 5433, "admin-pw")
    assert (cfg.shared_db, cfg.shared_user) == ("demo", "demo_owner")
    assert (cfg.db_prefix, cfg.user_prefix) == ("bicourse_db", "bicourse_user")
    assert "admin-pw" not in repr(cfg)


def test_create_database_for_a_user(mate):
    assert postgresql.create_postgresql_db("bicourse_db_05", "bicourse_user_05", "pw")
    assert mate.calls == [
        ("create_db", "bicourse_db_05", "bicourse_user_05", "pw"),
        ("grant_shared_access", "bicourse_user_05"),
    ]


def test_database_works_without_the_demo_database(mate, caplog):
    mate.fail["grant_shared_access"] = DBUserNotExistsException("no demo")
    assert postgresql.create_postgresql_db("d", "u", "pw") is True
    assert "cannot read the demo database" in caplog.text


def test_create_database_errors(mate):
    mate.fail["create_db"] = DatabaseAlreadyExistsException("Database 'd' exists")
    assert postgresql.create_postgresql_db("d", "u", "pw") is False
    with pytest.raises(postgresql.PostgreSQLError, match="Database 'd' exists"):
        postgresql.create_database("d", "u", "pw")


def test_next_database_number(mate):
    assert postgresql.next_database_number() == 5
    mate.fail["show_next_db_name"] = down()
    assert postgresql.next_database_number() is None


def test_existing_databases(mate):
    assert postgresql.existing_databases() == {"bicourse_db_01", "bicourse_db_04"}
    assert postgresql.database_exists("bicourse_db_04") is True
    mate.fail["list_dbs"] = mate.fail["database_exists"] = down()
    assert postgresql.existing_databases() is None
    assert postgresql.database_exists("x") is None


def test_set_password(mate):
    postgresql.set_password("bicourse_user_01", "new")
    assert mate.calls == [("set_user_password", "bicourse_user_01", "new")]
    mate.fail["set_user_password"] = DBUserNotExistsException("Role is not there")
    with pytest.raises(postgresql.PostgreSQLError, match="Role is not there"):
        postgresql.set_password("x", "y")


def test_grant_rights_to_own_public_schema(mate):
    assert postgresql.grant_rights_to_own_public_schema("d", "u") is True
    mate.fail["grant_public_schema_rights"] = down()
    assert postgresql.grant_rights_to_own_public_schema("d", "u") is False


def test_demo_database(mate):
    assert postgresql.init_postgresql_with_demo_user() is True
    assert mate.calls == [("create_shared_db",)]


def test_existing_demo_database_is_kept(mate):
    mate.fail["create_shared_db"] = DatabaseAlreadyExistsException("exists")
    assert postgresql.init_postgresql_with_demo_user() is True
    assert mate.calls[-1] == ("harden_shared_schema",)

    mate.fail["create_shared_db"] = down()
    assert postgresql.init_postgresql_with_demo_user() is False


def test_readonly_user_for_the_demo_database(mate):
    assert postgresql.create_postgresql_readonly_user_for_demo_db("reader", "pw")
    assert mate.calls == [("create_shared_user_readonly", "reader", "pw")]

    mate.fail["create_shared_user_readonly"] = DBUserAlreadyExistsException("exists")
    assert postgresql.create_postgresql_readonly_user_for_demo_db("reader", "pw")
    assert mate.calls[-1] == ("grant_shared_access", "reader")


class FakeCursor:
    def __init__(self, version="15.8"):
        self.version = version

    def execute(self, statement):
        self.statement = statement

    def fetchone(self):
        return [self.version]


def fake_connect(error=None, seen=None):
    @contextmanager
    def connect(cfg, database, user, password):
        if seen is not None:
            seen.append((database, user, password))
        if error is not None:
            raise error
        yield FakeCursor()

    return connect


def test_server_status(settings, monkeypatch):
    seen = []
    monkeypatch.setattr(postgresql, "connect", fake_connect(seen=seen))
    status = postgresql.server_status()
    assert (status.ok, status.address, status.text) == (
        True,
        "localhost:5432",
        "PostgreSQL 15.8",
    )
    assert seen == [("postgres", "postgres", "postgres")]

    monkeypatch.setattr(postgresql, "connect", fake_connect(down()))
    status = postgresql.server_status()
    assert status.ok is False and "connection refused" in status.text


@pytest.mark.parametrize(
    "message,result",
    [
        (None, postgresql.ACCESS_OK),
        (
            'FATAL:  password authentication failed for user "u"',
            postgresql.ACCESS_LOGIN_FAILED,
        ),
        ('FATAL:  role "u" does not exist', postgresql.ACCESS_LOGIN_FAILED),
        ('FATAL:  database "d" does not exist', postgresql.ACCESS_NO_DATABASE),
        ("could not translate host name", postgresql.ACCESS_DOWN),
    ],
)
def test_check_user_access(settings, monkeypatch, message, result):
    error = DBConnectionException(f"Could not connect: {message}") if message else None
    monkeypatch.setattr(postgresql, "connect", fake_connect(error))
    assert postgresql.check_user_access("d", "u", "pw") == result


# ----- MariaDB -----


class FakeMariaCursor:
    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        if self.fail:
            raise RuntimeError("denied")
        self.log.append((statement, params))


class FakeMariaConnection:
    def __init__(self, log, fail=False):
        self.log, self.fail, self.closed = log, fail, False

    def cursor(self):
        return FakeMariaCursor(self.log, self.fail)

    def close(self):
        self.closed = True


def test_create_mariadb_database(use_settings, monkeypatch):
    use_settings(MARIADB_DB_HOST="mariadb", MARIADB_DB_HOST_PORT="3307")
    log, connections = [], []

    def connect(**kwargs):
        connections.append((kwargs, FakeMariaConnection(log)))
        return connections[-1][1]

    monkeypatch.setattr(mariadb.pymysql, "connect", connect)
    assert (
        mariadb.create_mariadb_db("mariadb_wordpress_db_7001", "mariadb_user_01", "pw")
        is True
    )

    kwargs, connection = connections[0]
    assert (kwargs["host"], kwargs["port"], kwargs["user"]) == (
        "mariadb",
        3307,
        "mariadb",
    )
    assert connection.closed
    assert log[0] == ("CREATE DATABASE `mariadb_wordpress_db_7001`", None)
    assert log[1][1] == ("mariadb_user_01", "pw")
    assert "`mariadb_wordpress_db_7001`.*" in log[1][0]
    assert log[2][0] == "FLUSH PRIVILEGES"


def test_mariadb_rejects_unsafe_names(settings, monkeypatch):
    def connect(**_kwargs):
        raise AssertionError("must not connect")

    monkeypatch.setattr(mariadb.pymysql, "connect", connect)
    assert mariadb.create_mariadb_db("db`; DROP", "user", "pw") is False
    assert mariadb.create_mariadb_db("db", "user'x", "pw") is False


def test_mariadb_errors(settings, monkeypatch):
    def down(**_kwargs):
        raise ConnectionError("down")

    monkeypatch.setattr(mariadb.pymysql, "connect", down)
    assert mariadb.create_mariadb_db("db", "user", "pw") is False

    monkeypatch.setattr(
        mariadb.pymysql, "connect", lambda **_k: FakeMariaConnection([], fail=True)
    )
    assert mariadb.create_mariadb_db("db", "user", "pw") is False
