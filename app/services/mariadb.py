"""Databases and users in the MariaDB service for the students"""

import logging
import re

import pymysql

from app.config import get_settings

logger = logging.getLogger(__name__)

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def create_mariadb_db(db_name: str, db_user: str, db_password: str) -> bool:
    """Creates a database and a user with all rights for it"""

    if not NAME_PATTERN.match(db_name) or not NAME_PATTERN.match(db_user):
        logger.error("Not a valid MariaDB name: %s / %s", db_name, db_user)
        return False

    settings = get_settings()
    connection = None
    try:
        connection = pymysql.connect(
            host=settings.mariadb_db_host,
            port=settings.mariadb_db_host_port,
            user=settings.mariadb_admin_user,
            password=settings.mariadb_admin_password.get_secret_value(),
            connect_timeout=15,
        )
        with connection.cursor() as cursor:
            # names are checked above: they cannot be passed as parameters
            cursor.execute(f"CREATE DATABASE `{db_name}`")
            cursor.execute(
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO %s@'%%' IDENTIFIED BY %s",
                (db_user, db_password),
            )
            cursor.execute("FLUSH PRIVILEGES")
        return True
    except Exception as error:
        logger.error("MariaDB error for database %s: %s", db_name, error)
        return False
    finally:
        if connection is not None:
            connection.close()
