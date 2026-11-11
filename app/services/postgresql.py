"""Databases and users in the PostgreSQL service for the students"""

import logging

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app.config import POSTGRESQL_DB_PREFIX, get_settings

logger = logging.getLogger(__name__)


def _connect(database: str, user: str = None, password: str = None):
    settings = get_settings()
    connection = psycopg2.connect(
        user=user or settings.postgresql_admin_user,
        password=password or settings.postgresql_admin_password.get_secret_value(),
        host=settings.postgresql_db_host,
        port=settings.postgresql_db_host_port,
        database=database,
        connect_timeout=15,
    )
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return connection


def _execute(
    statements: list, database: str, user: str = None, password: str = None
) -> bool:
    """Runs the statements (as the admin, if no user is given). Returns True on success."""

    connection = None
    try:
        connection = _connect(database, user, password)
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        return True
    except Exception as error:
        logger.error("PostgreSQL error in database %s: %s", database, error)
        return False
    finally:
        if connection is not None:
            connection.close()


def _sql(template: str, **names) -> sql.Composed:
    """Builds a statement. The names are quoted as identifiers."""

    return sql.SQL(template).format(
        **{key: sql.Identifier(value) for key, value in names.items()}
    )


def next_database_number() -> int | None:
    """Gets the number for the next database of a user (None if PostgreSQL is not reachable).

    Counts the databases of the users: do not delete single databases.
    """

    settings = get_settings()
    connection = None
    try:
        connection = _connect(settings.postgresql_db_name)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) + 1 FROM pg_database WHERE datname LIKE %s",
                (f"%{POSTGRESQL_DB_PREFIX}%",),
            )
            return int(cursor.fetchone()[0])
    except Exception as error:
        logger.error("Cannot get the next database number: %s", error)
        return None
    finally:
        if connection is not None:
            connection.close()


def create_postgresql_db(db_name: str, db_user: str, db_password: str) -> bool:
    """Creates a database (and a role with its name) and the user that owns it.

    The user can also read the demo database.
    """

    settings = get_settings()
    demo_db = settings.postgresql_demo_db

    _execute(
        [
            _sql(
                "CREATE ROLE {role} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOLOGIN",
                role=db_name,
            ),
            sql.SQL(
                "CREATE ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN "
                "ENCRYPTED PASSWORD {}"
            ).format(sql.Identifier(db_user), sql.Literal(db_password)),
            _sql("GRANT {role} TO {user}", role=db_name, user=db_user),
            _sql("CREATE DATABASE {db} WITH OWNER = {user}", db=db_name, user=db_user),
            _sql("REVOKE ALL ON DATABASE {db} FROM public", db=db_name),
            _sql("GRANT CONNECT ON DATABASE {db} TO {user}", db=demo_db, user=db_user),
        ],
        database=settings.postgresql_db_name,
    )

    # only the owner can pass on the rights for its public schema
    is_created = _execute(
        [_sql("GRANT ALL ON SCHEMA public TO {user} WITH GRANT OPTION", user=db_user)],
        database=db_name,
        user=db_user,
        password=db_password,
    )

    grant_rights_to_own_public_schema(db_name, db_user)

    # only the demo user can give access to the tables of the demo database
    demo_granted = grant_select_on_demo_db(db_user)

    return is_created and demo_granted


def grant_select_on_demo_db(db_user: str) -> bool:
    settings = get_settings()
    return _execute(
        [
            _sql("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {user}", user=db_user),
            _sql(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {user}",
                user=db_user,
            ),
        ],
        database=settings.postgresql_demo_db,
        user=settings.postgresql_demo_user,
        password=settings.postgresql_demo_password.get_secret_value(),
    )


def grant_rights_to_own_public_schema(db_name: str, db_user: str) -> bool:
    """Lets the user create tables in the public schema of the user's database"""

    return _execute(
        [
            _sql("GRANT CREATE ON SCHEMA public TO {role}", role=db_name),
            _sql("GRANT CREATE ON SCHEMA public TO {user}", user=db_user),
        ],
        database=db_name,
    )


def init_postgresql_with_demo_user() -> bool:
    """Creates the demo database and its user"""

    settings = get_settings()
    return create_postgresql_db(
        db_name=settings.postgresql_demo_db,
        db_user=settings.postgresql_demo_user,
        db_password=settings.postgresql_demo_password.get_secret_value(),
    )


def create_postgresql_readonly_user_for_demo_db(
    readonly_db_user: str, readonly_db_password: str
) -> bool:
    """Creates a user that can only read the demo database"""

    settings = get_settings()
    demo_db = settings.postgresql_demo_db

    _execute(
        [
            sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                sql.Identifier(readonly_db_user), sql.Literal(readonly_db_password)
            ),
            _sql(
                "GRANT CONNECT ON DATABASE {db} TO {user}",
                db=demo_db,
                user=readonly_db_user,
            ),
        ],
        database=settings.postgresql_db_name,
    )

    # in the demo database, only the demo user creates tables
    _execute(
        [
            sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"),
            _sql(
                "GRANT CREATE ON SCHEMA public TO {user}",
                user=settings.postgresql_demo_user,
            ),
        ],
        database=demo_db,
    )

    return grant_select_on_demo_db(readonly_db_user)
