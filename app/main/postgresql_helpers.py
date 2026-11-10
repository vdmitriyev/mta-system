import traceback
from typing import Tuple

import psycopg2
from flask import current_app
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import and_

from .. import settings as settings
from ..extensions import db
from ..models import Users
from ..utils.uhelpers import to_json_sqla
from .mhelpers import get_user_data


def new_postgresql_db_names() -> Tuple[str, str, str]:
    """Gets a new name for a database and a user.

    Returns:
        Tuple[str, str, str]: a new database name, a new username, a user "order"
    """

    new_db_name, new_db_user, new_db_user_order = None, None, None

    # very simple method that simple takes the next int
    # won't work if users/databases will be deleted randomly

    sql_next_cnt = "SELECT count(*)+1 FROM pg_database where datname LIKE '%{dbNamePrefix}%';".format(
        dbNamePrefix=settings.POSTGRESQL_DB_PREFIX
    )
    connection = None
    try:
        connection = psycopg2.connect(
            user=current_app.config["POSTGRESQL_ADMIN_USER"],
            password=current_app.config["POSTGRESQL_ADMIN_PASSWORD"],
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=current_app.config["POSTGRESQL_DB_NAME"],
        )

        cursor = connection.cursor()
        cursor.execute(sql_next_cnt)
        sql_next_row = cursor.fetchone()

        new_db_user_order = sql_next_row[0]
        new_db_name = "{0}_{1}".format(
            settings.POSTGRESQL_DB_PREFIX, str(sql_next_row[0]).zfill(2)
        )
        new_db_user = "{0}_{1}".format(
            settings.POSTGRESQL_USER_PREFIX, str(sql_next_row[0]).zfill(2)
        )

    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
    finally:
        if connection:
            cursor.close()
            connection.close()
            current_app.logger.info("PostgreSQL connection was closed")
        else:
            current_app.logger.error("PostgreSQL connection is None")

    return new_db_name, new_db_user, new_db_user_order


def create_postgresql_db(
    db_name: str, db_user: str, db_password: str, verbose=True
) -> bool:
    """Creates a new database and a user in a PostgreSQL

    Args:
        db_name (str): a name (and a role) of a new database
        db_user (str): a admin user of a new database
        db_password (str): a password of a new database user
        verbose (bool, optional): _description_. Defaults to True.

    Returns:
        bool: True if a database was created
    """

    is_created = False

    sql_crt_role_01 = """CREATE ROLE {0} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOLOGIN;""".format(
        db_name
    )
    sql_crt_role_02 = """CREATE ROLE {0} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN ENCRYPTED PASSWORD '{1}';""".format(
        db_user, db_password
    )

    sql_grant_01 = """GRANT {0} TO {1};""".format(db_name, db_user)
    sql_grant_demo_01 = """GRANT CONNECT ON DATABASE {db_demo} TO {db_user}""".format(
        db_demo=current_app.config["POSTGRESQL_DEMO_DB"], db_user=db_user
    )
    sql_crt_db = """CREATE DATABASE {0} WITH OWNER={1};""".format(db_name, db_user)
    sql_revoke = """REVOKE ALL ON DATABASE {0} FROM public;""".format(db_name)

    connection = None
    try:
        connection = psycopg2.connect(
            user=current_app.config["POSTGRESQL_ADMIN_USER"],
            password=current_app.config["POSTGRESQL_ADMIN_PASSWORD"],
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=current_app.config["POSTGRESQL_DB_NAME"],
        )

        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = connection.cursor()

        # PostgreSQL Connection properties
        if verbose:
            current_app.logger.info(
                "PostgreSQL DNS parameters: {0}".format(
                    connection.get_dsn_parameters(), "\n"
                )
            )

        # PostgreSQL version
        # if verbose:
        #     cursor.execute("SELECT version();")
        #     record = cursor.fetchone()
        #     print('[i] You are connected to the following PostgreSQL database: {0}'.format(record[0]))

        cursor.execute(sql_crt_role_01)
        cursor.execute(sql_crt_role_02)
        cursor.execute(sql_grant_01)
        cursor.execute(sql_crt_db)
        cursor.execute(sql_revoke)
        cursor.execute(sql_grant_demo_01)
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
        is_created = False
    finally:
        if connection:
            cursor.close()
            connection.close()
            current_app.logger.info("PostgreSQL connection was closed")
        else:
            current_app.logger.error("PostgreSQL connection is None")

    # open connection to newly created database to provide it with some grants
    sql_newdb_grant = """GRANT ALL ON SCHEMA public TO {0} WITH GRANT OPTION;""".format(
        db_user
    )
    connection_new_db = None

    try:
        current_app.logger.info("Connecting to the new database")
        connection_new_db = psycopg2.connect(
            user=db_user,
            password=db_password,
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=db_name,
        )
        connection_new_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor_new_db = connection_new_db.cursor()
        cursor_new_db.execute(sql_newdb_grant)
        is_created = True
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
        is_created = False
    finally:
        if connection_new_db:
            cursor_new_db.close()
            connection_new_db.close()
        else:
            current_app.logger.error(
                "PostgreSQL connection to the NEW DATABASE is None"
            )

    # grand additional grants for the new user to the public schema
    grand_rights_to_own_public_schema(db_name, db_user)

    #
    # open connection to demo database to provide it with some grants
    # this can be done only under demo user profile
    #
    sql_demodb_grant = (
        """GRANT SELECT ON ALL TABLES IN SCHEMA public TO {db_user};""".format(
            db_user=db_user
        )
    )
    sql_demodb_grant_alt = """ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {db_user};""".format(
        db_user=db_user
    )
    connection_demo_db = None
    try:
        current_app.logger.info("Connecting to the demo database")
        connection_demo_db = psycopg2.connect(
            user=current_app.config["POSTGRESQL_DEMO_USER"],
            password=current_app.config["POSTGRESQL_DEMO_PASSWORD"],
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=current_app.config["POSTGRESQL_DEMO_DB"],
        )
        connection_demo_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor_demo_db = connection_demo_db.cursor()
        cursor_demo_db.execute(sql_demodb_grant)
        cursor_demo_db.execute(sql_demodb_grant_alt)
        is_created = True
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
        is_created = False
    finally:
        if connection_demo_db:
            cursor_demo_db.close()
            cursor_demo_db.close()
        else:
            current_app.logger.error(
                "PostgreSQL connection to the DEMO DATABASE is None"
            )

    return is_created


def grand_rights_to_own_public_all() -> None:
    """Grants right to the user"""

    source_code = current_app.config["COURSE_SECURITY_CODE"]

    users = []
    users_lst = (
        db.session.query(Users)
        .filter(and_(Users.deleted == False, Users.course_code == source_code))
        .order_by(Users.email.asc())
        .all()
    )

    for index, user in enumerate(users_lst):
        user_json = to_json_sqla(user)
        user_data = get_user_data(user_json["url_hash"])
        if "postgresql_service" in user_data:
            pg_user_data = user_data["postgresql_service"]
            # print(pg_user_data)
            grand_rights_to_own_public_schema(
                pg_user_data["postgresql_db"], pg_user_data["postgresql_user"]
            )
        else:
            current_app.logger.warning(
                f'Not data of the postgresql_service found for the users: {user_json["internal_email"]}'
            )


def grand_rights_to_own_public_schema(db_name: str, db_user: str) -> None:
    """Creates a new database and a user in a PostgreSQL

    Args:
        db_name (str): a name (and a role) of a new database
        db_user (str): a admin user of a new database
        verbose (bool, optional): _description_. Defaults to True.
    """

    # open connection to newly created database to provide it with some grants
    sql_newdb_grant_01 = """GRANT CREATE ON SCHEMA public TO {0}""".format(db_name)
    sql_newdb_grant_02 = """GRANT CREATE ON SCHEMA public TO {0}""".format(db_user)

    connection_new_db = None
    try:
        current_app.logger.info("Connecting to the new database")
        connection_new_db = psycopg2.connect(
            user=current_app.config["POSTGRESQL_ADMIN_USER"],
            password=current_app.config["POSTGRESQL_ADMIN_PASSWORD"],
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=db_name,
        )

        connection_new_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor_new_db = connection_new_db.cursor()
        cursor_new_db.execute(sql_newdb_grant_01)
        cursor_new_db.execute(sql_newdb_grant_02)
        is_created = True
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
        is_created = False
    finally:
        if connection_new_db:
            cursor_new_db.close()
            connection_new_db.close()
        else:
            current_app.logger.error(
                "PostgreSQL connection to the NEW DATABASE is None"
            )


def init_postgresql_with_demo_user():
    """Initiate PostgreSQL demo database - required for a teaching course.
    This function should be run, if needed.
    For a moment, it won't be executed automatically by the system.
    """

    # create demo user and database
    if create_postgresql_db(
        db_name=current_app.config["POSTGRESQL_DEMO_DB"],
        db_user=current_app.config["POSTGRESQL_DEMO_USER"],
        db_password=current_app.config["POSTGRESQL_DEMO_PASSWORD"],
    ):
        current_app.logger.info("User and database in PostgreSQL were created")
    else:
        current_app.logger.warning("User and database in PostgreSQL were NOT created.")


def create_postgresql_readonly_user_for_demo_db(
    readonly_db_user: str, readonly_db_password: str
) -> bool:
    """Creates readonly database user in the demo_db

    Args:
        readonly_db_user (str): database user name for readonly access
        readonly_db_password (str): database user password for readonly access

    Returns:
        bool: was created or not
    """

    is_created = False

    sql_crt_role_01 = (
        """CREATE USER {user_name} WITH PASSWORD '{user_password}';""".format(
            user_name=readonly_db_user, user_password=readonly_db_password
        )
    )
    sql_grant_01 = """GRANT CONNECT ON DATABASE {db_name} TO {user_name};""".format(
        db_name=current_app.config["POSTGRESQL_DEMO_DB"], user_name=readonly_db_user
    )

    connection = None
    try:
        connection = psycopg2.connect(
            user=current_app.config["POSTGRESQL_ADMIN_USER"],
            password=current_app.config["POSTGRESQL_ADMIN_PASSWORD"],
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=current_app.config["POSTGRESQL_DB_NAME"],
        )

        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = connection.cursor()

        cursor.execute(sql_crt_role_01)
        cursor.execute(sql_grant_01)
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
        is_created = False
    finally:
        if connection:
            cursor.close()
            connection.close()
            current_app.logger.info("PostgreSQL connection was closed")
        else:
            current_app.logger.error("PostgreSQL connection is None")

    #
    # open connection to DEMO database with postgre (super user) user rights to revoke create rights
    #

    sql_demodb_grant_01 = """REVOKE CREATE ON SCHEMA public FROM PUBLIC;"""
    sql_demodb_grant_02 = """GRANT CREATE ON SCHEMA public to {db_user};""".format(
        db_user=current_app.config["POSTGRESQL_DEMO_USER"]
    )

    connection = None
    try:
        connection = psycopg2.connect(
            user=current_app.config["POSTGRESQL_ADMIN_USER"],
            password=current_app.config["POSTGRESQL_ADMIN_PASSWORD"],
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=current_app.config["POSTGRESQL_DEMO_DB"],
        )

        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = connection.cursor()

        cursor.execute(sql_demodb_grant_01)
        cursor.execute(sql_demodb_grant_02)
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
        is_created = False
    finally:
        if connection:
            cursor.close()
            connection.close()
            current_app.logger.info("PostgreSQL connection was closed")
        else:
            current_app.logger.error("PostgreSQL connection is None")

    #
    # open connection to demo database to provide it with some grants
    # this can be done only under demo user profile
    #
    sql_demodb_grant = (
        """GRANT SELECT ON ALL TABLES IN SCHEMA public TO {db_user};""".format(
            db_user=readonly_db_user
        )
    )
    sql_demodb_grant_alt = """ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {db_user};""".format(
        db_user=readonly_db_user
    )
    connection_demo_db = None
    try:
        current_app.logger.info("Connecting to the demo database")
        connection_demo_db = psycopg2.connect(
            user=current_app.config["POSTGRESQL_DEMO_USER"],
            password=current_app.config["POSTGRESQL_DEMO_PASSWORD"],
            host=current_app.config["POSTGRESQL_DB_HOST"],
            port=current_app.config["POSTGRESQL_DB_HOST_PORT"],
            database=current_app.config["POSTGRESQL_DEMO_DB"],
        )
        connection_demo_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor_demo_db = connection_demo_db.cursor()
        cursor_demo_db.execute(sql_demodb_grant)
        cursor_demo_db.execute(sql_demodb_grant_alt)
        is_created = True
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
        is_created = False
    finally:
        if connection_demo_db:
            cursor_demo_db.close()
            cursor_demo_db.close()
        else:
            current_app.logger.error(
                "PostgreSQL connection to the DEMO DATABASE is None"
            )

    return is_created
