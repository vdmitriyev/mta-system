import time
import traceback

import pymysql
from flask import current_app


def create_mariadb_db(db_name: str, db_user: str, db_password: str):
    """Creates a MariaDB user and database

    Args:
        db_name (str): _description_
        db_user (str): _description_
        db_password (str): _description_
    """

    is_created = False
    conn, cur = None, None

    try:
        conn = pymysql.connect(
            host=current_app.config["MARIADB_DB_HOST"],
            user=current_app.config["MARIADB_ADMIN_USER"],
            password=current_app.config["MARIADB_ADMIN_PASSWORD"],
        )
        cur = conn.cursor()
        new_db_sql = f"CREATE DATABASE {db_name}"
        new_user_sql = f"GRANT ALL privileges on {db_name}.* TO '{db_user}'@'%' identified by '{db_password}'"
        flush_sql = f"flush privileges"
        cur.execute(new_db_sql)
        time.sleep(0.5)
        cur.execute(new_user_sql)
        time.sleep(0.5)
        cur.execute(flush_sql)
        time.sleep(0.5)
        is_created = True
    except Exception as ex:
        current_app.logger.warning(f"Error while working with PostgreSQL: {ex}")
        current_app.logger.error(traceback.format_exc())
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            current_app.logger.info("MariaDB connection was closed")
        else:
            current_app.logger.error("MariaDB connection is None")

    return is_created
