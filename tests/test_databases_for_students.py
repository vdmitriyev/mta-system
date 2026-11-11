"""PostgreSQL and MariaDB services: the tests record the SQL instead of running it"""

import pytest
from psycopg2 import sql

from app.services import mariadb, postgresql


def render(statement) -> str:
    """Shows a psycopg2 statement as text (identifiers in double quotes)"""

    if isinstance(statement, str):
        return statement
    if isinstance(statement, sql.SQL):
        return statement.string
    if isinstance(statement, sql.Identifier):
        return ".".join(f'"{part}"' for part in statement.strings)
    if isinstance(statement, sql.Literal):
        return f"'{statement.wrapped}'"
    return "".join(render(part) for part in statement.seq)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        text = render(statement)
        if self.connection.server.fail_on and self.connection.server.fail_on in text:
            raise RuntimeError("statement failed")
        self.connection.server.statements.append(
            (self.connection.database, self.connection.user, text, params)
        )

    def fetchone(self):
        return (self.connection.server.next_number,)


class FakeConnection:
    def __init__(self, server, **kwargs):
        self.server = server
        self.database = kwargs.get("database")
        self.user = kwargs.get("user")
        self.kwargs = kwargs
        self.closed = False

    def set_isolation_level(self, _level):
        pass

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class FakeServer:
    def __init__(self):
        self.statements = []
        self.connections = []
        self.fail_on = None
        self.down = False
        self.next_number = 5

    def connect(self, **kwargs):
        if self.down:
            raise ConnectionError("server is down")
        connection = FakeConnection(self, **kwargs)
        self.connections.append(connection)
        return connection

    def sql_for(self, database):
        return [text for db, _user, text, _params in self.statements if db == database]


@pytest.fixture
def pg(settings, monkeypatch):
    server = FakeServer()
    monkeypatch.setattr(postgresql.psycopg2, "connect", server.connect)
    return server


def test_next_database_number(pg):
    assert postgresql.next_database_number() == 5
    _db, _user, text, params = pg.statements[0]
    assert "pg_database" in text
    assert params == ("%bicourse_db%",)
    assert all(connection.closed for connection in pg.connections)


def test_next_database_number_without_server(pg):
    pg.down = True
    assert postgresql.next_database_number() is None


def test_create_database_for_a_user(pg):
    assert (
        postgresql.create_postgresql_db("bicourse_db_05", "bicourse_user_05", "pw'1")
        is True
    )

    admin_sql = pg.sql_for("postgres")
    assert admin_sql == [
        'CREATE ROLE "bicourse_db_05" NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOLOGIN',
        'CREATE ROLE "bicourse_user_05" NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN '
        "ENCRYPTED PASSWORD 'pw'1'",
        'GRANT "bicourse_db_05" TO "bicourse_user_05"',
        'CREATE DATABASE "bicourse_db_05" WITH OWNER = "bicourse_user_05"',
        'REVOKE ALL ON DATABASE "bicourse_db_05" FROM public',
        'GRANT CONNECT ON DATABASE "db_demo" TO "bicourse_user_05"',
    ]

    own = [
        (user, text) for db, user, text, _ in pg.statements if db == "bicourse_db_05"
    ]
    assert own[0] == (
        "bicourse_user_05",
        'GRANT ALL ON SCHEMA public TO "bicourse_user_05" WITH GRANT OPTION',
    )
    assert own[1:] == [
        ("postgres", 'GRANT CREATE ON SCHEMA public TO "bicourse_db_05"'),
        ("postgres", 'GRANT CREATE ON SCHEMA public TO "bicourse_user_05"'),
    ]

    demo = [(user, text) for db, user, text, _ in pg.statements if db == "db_demo"]
    assert demo[0] == (
        "db_user_demo",
        'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "bicourse_user_05"',
    )
    assert all(connection.closed for connection in pg.connections)


def test_names_are_quoted_as_identifiers(pg):
    postgresql.create_postgresql_db('x"; DROP DATABASE postgres; --', "user", "pw")
    assert pg.sql_for("postgres")[0].startswith('CREATE ROLE "x"; DROP DATABASE')
    statement = postgresql._sql("GRANT {role} TO {user}", role="a", user="b")
    assert isinstance(statement.seq[1], sql.Identifier)


def test_create_database_fails_if_a_grant_fails(pg):
    pg.fail_on = "WITH GRANT OPTION"
    assert postgresql.create_postgresql_db("d", "u", "pw") is False


def test_create_database_without_server(pg):
    pg.down = True
    assert postgresql.create_postgresql_db("d", "u", "pw") is False


def test_demo_database(pg):
    assert postgresql.init_postgresql_with_demo_user() is True
    assert 'CREATE DATABASE "db_demo" WITH OWNER = "db_user_demo"' in pg.sql_for(
        "postgres"
    )


def test_readonly_user_for_the_demo_database(pg):
    assert (
        postgresql.create_postgresql_readonly_user_for_demo_db("reader", "pw") is True
    )
    assert pg.sql_for("postgres") == [
        "CREATE USER \"reader\" WITH PASSWORD 'pw'",
        'GRANT CONNECT ON DATABASE "db_demo" TO "reader"',
    ]
    assert pg.sql_for("db_demo") == [
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
        'GRANT CREATE ON SCHEMA public TO "db_user_demo"',
        'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "reader"',
        'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "reader"',
    ]


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
