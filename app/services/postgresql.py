"""Databases and users in the PostgreSQL service for the students.

The SQL is done by the package dbsetupmate. Its "shared" database is the demo
database of the course: every student can read it.
"""

import logging
from dataclasses import dataclass

from dbsetupmate import (
    DatabaseAlreadyExistsException,
    DBSetupMateException,
    DBUserAlreadyExistsException,
    PostgresMate,
    PostgreSQLConfig,
)
from dbsetupmate.postgresql import connect

from app.config import POSTGRESQL_DB_PREFIX, POSTGRESQL_USER_PREFIX, get_settings

CONNECT_TIMEOUT_SECONDS = 5

# Results of check_user_access
ACCESS_OK = "OK"
ACCESS_LOGIN_FAILED = "LOGIN FAILED"
ACCESS_NO_DATABASE = "NO DATABASE"
ACCESS_DOWN = "DOWN"

logger = logging.getLogger(__name__)


class PostgreSQLError(Exception):
    """An action in PostgreSQL failed. The text is shown to the admin."""


@dataclass
class ServerStatus:
    ok: bool
    address: str
    text: str


def config() -> PostgreSQLConfig:
    settings = get_settings()
    return PostgreSQLConfig(
        host=settings.postgresql_db_host,
        port=settings.postgresql_db_host_port,
        database=settings.postgresql_db_name,
        admin_user=settings.postgresql_admin_user,
        admin_password=settings.postgresql_admin_password.get_secret_value(),
        shared_db=settings.postgresql_demo_db,
        shared_user=settings.postgresql_demo_user,
        shared_password=settings.postgresql_demo_password.get_secret_value(),
        shared_user_readonly=settings.postgresql_demo_user_readonly,
        shared_user_readonly_password=(
            settings.postgresql_demo_user_readonly_password.get_secret_value()
        ),
        db_prefix=POSTGRESQL_DB_PREFIX,
        user_prefix=POSTGRESQL_USER_PREFIX,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        application_name="mta-system",
    )


def mate() -> PostgresMate:
    return PostgresMate(config())


def _error(error: DBSetupMateException) -> PostgreSQLError:
    return PostgreSQLError(error.message)


# ---- checks ----


def server_status() -> ServerStatus:
    """Connects as the admin and reads the version of the server"""

    cfg = config()
    address = f"{cfg.host}:{cfg.port}"
    try:
        with connect(cfg, cfg.database, cfg.admin_user, cfg.admin_password) as cursor:
            cursor.execute("SHOW server_version")
            version = cursor.fetchone()[0]
    except DBSetupMateException as error:
        logger.error("PostgreSQL server %s is not reachable: %s", address, error)
        return ServerStatus(False, address, error.message)
    return ServerStatus(True, address, f"PostgreSQL {version}")


def check_user_access(db_name: str, db_user: str, password: str) -> str:
    """Logs in as the user into the user's database. Returns one of the ACCESS_* values."""

    try:
        with connect(config(), db_name, db_user, password) as cursor:
            cursor.execute("SELECT 1")
        return ACCESS_OK
    except DBSetupMateException as error:
        # errors while connecting have no SQLSTATE: read the text of the server
        text = error.message.lower()
        if "password authentication failed" in text or (
            "role" in text and "does not exist" in text
        ):
            return ACCESS_LOGIN_FAILED
        if "database" in text and "does not exist" in text:
            return ACCESS_NO_DATABASE
        return ACCESS_DOWN


def existing_databases() -> set | None:
    """Names of the databases of the students (None if the server is not reachable)"""

    try:
        return {entry.database for entry in mate().list_dbs()}
    except DBSetupMateException as error:
        logger.error("Cannot list the PostgreSQL databases: %s", error)
        return None


def database_exists(name: str) -> bool | None:
    """True if the database is on the server (None if the server is not reachable)"""

    try:
        return mate().database_exists(name)
    except DBSetupMateException as error:
        logger.error("Cannot check the database %s: %s", name, error)
        return None


def next_database_number() -> int | None:
    """Number for the next database of a user (None if PostgreSQL is not reachable).

    Continues after the highest number in use, so deleted databases cause no collision.
    """

    try:
        return mate().show_next_db_name().order
    except DBSetupMateException as error:
        logger.error("Cannot get the next database number: %s", error)
        return None


# ---- changes ----


def create_database(db_name: str, db_user: str, db_password: str) -> None:
    """Creates a database, its owner role and the login user. The user can read the demo database.

    Raises PostgreSQLError, e.g. if the database already exists.
    """

    manager = mate()
    try:
        manager.create_db(db_name, db_user, db_password)
    except DBSetupMateException as error:
        raise _error(error) from error
    try:
        manager.grant_shared_access(db_user)
    except DBSetupMateException as error:
        # the own database works without the demo database
        logger.warning("%s cannot read the demo database: %s", db_user, error)


def create_postgresql_db(db_name: str, db_user: str, db_password: str) -> bool:
    """Like create_database, but returns False instead of an error"""

    try:
        create_database(db_name, db_user, db_password)
        return True
    except PostgreSQLError as error:
        logger.error("Database %s was not created: %s", db_name, error)
        return False


def set_password(db_user: str, password: str) -> None:
    """Sets the password of a login user in PostgreSQL. Raises PostgreSQLError."""

    try:
        mate().set_user_password(db_user, password)
    except DBSetupMateException as error:
        raise _error(error) from error


def grant_rights_to_own_public_schema(db_name: str, db_user: str) -> bool:
    """Lets the user create tables in the public schema of the user's database"""

    try:
        mate().grant_public_schema_rights(db_name, db_user)
        return True
    except DBSetupMateException as error:
        logger.error("Rights in %s were not granted: %s", db_name, error)
        return False


def init_postgresql_with_demo_user() -> bool:
    """Creates the demo database and its owner. An existing demo database is kept."""

    manager = mate()
    try:
        manager.create_shared_db()
    except (DatabaseAlreadyExistsException, DBUserAlreadyExistsException) as error:
        logger.info("Demo database is already there: %s", error)
        try:
            manager.harden_shared_schema()
        except DBSetupMateException as hardening_error:
            logger.error("Demo database was not checked: %s", hardening_error)
            return False
    except DBSetupMateException as error:
        logger.error("Demo database was not created: %s", error)
        return False
    return True


def create_postgresql_readonly_user_for_demo_db(
    readonly_db_user: str, readonly_db_password: str
) -> bool:
    """Creates a user that can only read the demo database. An existing user is kept."""

    manager = mate()
    try:
        manager.create_shared_user_readonly(readonly_db_user, readonly_db_password)
    except DBUserAlreadyExistsException:
        logger.info("Read-only user %s is already there", readonly_db_user)
        try:
            manager.grant_shared_access(readonly_db_user)
        except DBSetupMateException as error:
            logger.error("Read-only access was not granted: %s", error)
            return False
    except DBSetupMateException as error:
        logger.error("Read-only user was not created: %s", error)
        return False
    return True
