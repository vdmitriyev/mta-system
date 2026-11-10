import os
from datetime import datetime


def get_connection_string():
    """Returns the URI of the SQLite database that stores the mta-system data"""

    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.environ.get("MTAS_DB_PATH") or os.path.join("data", "mta-system.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(basedir, db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return f"sqlite:///{db_path}"


class EMailServerConfig:

    # e-mail settings
    MAIL_SERVER = os.environ.get("MAIL_SERVER") or "localhost"
    MAIL_PORT = os.environ.get("MAIL_PORT") or 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME") or None
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD") or None
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER") or None
    MAIL_ADMIN_NOTIFICATIONS = os.environ.get("MAIL_ADMIN_NOTIFICATIONS") or None


class ServiceCreationConfig:

    # Disable/enable creation of the services for users
    CREATE_POSTGRESQL_SERVICE = os.environ.get("CREATE_POSTGRESQL_SERVICE") or "False"
    CREATE_POSTGRESQL_SERVICE = CREATE_POSTGRESQL_SERVICE.upper() == "TRUE"

    CREATE_PG4ADMIN_SERVICE = os.environ.get("CREATE_PG4ADMIN_SERVICE") or "False"
    CREATE_PG4ADMIN_SERVICE = CREATE_PG4ADMIN_SERVICE.upper() == "TRUE"

    CREATE_JUPYTERHUB_SERVICE = os.environ.get("CREATE_JUPYTERHUB_SERVICE") or "False"
    CREATE_JUPYTERHUB_SERVICE = CREATE_JUPYTERHUB_SERVICE.upper() == "TRUE"

    CREATE_METABASE_SERVICE = os.environ.get("CREATE_METABASE_SERVICE") or "False"
    CREATE_METABASE_SERVICE = CREATE_METABASE_SERVICE.upper() == "TRUE"

    CREATE_OPENREFINE_SERVICE = os.environ.get("CREATE_OPENREFINE_SERVICE") or "False"
    CREATE_OPENREFINE_SERVICE = CREATE_OPENREFINE_SERVICE.upper() == "TRUE"

    CREATE_MARIADB_SERVICE = os.environ.get("CREATE_MARIADB_SERVICE") or "False"
    CREATE_MARIADB_SERVICE = CREATE_MARIADB_SERVICE.upper() == "TRUE"

    CREATE_WORDPRESS_SERVICE = os.environ.get("CREATE_WORDPRESS_SERVICE") or "False"
    CREATE_WORDPRESS_SERVICE = CREATE_WORDPRESS_SERVICE.upper() == "TRUE"

    CREATE_NIFI_SERVICE = os.environ.get("CREATE_NIFI_SERVICE") or "False"
    CREATE_NIFI_SERVICE = CREATE_NIFI_SERVICE.upper() == "TRUE"

    CREATE_SUPERSET_SERVICE = os.environ.get("CREATE_SUPERSET_SERVICE") or "False"
    CREATE_SUPERSET_SERVICE = CREATE_SUPERSET_SERVICE.upper() == "TRUE"

    if not CREATE_MARIADB_SERVICE and CREATE_WORDPRESS_SERVICE:
        raise Exception(
            "Wordpress service requires creation of the MariaDB service config"
        )


class PostgreSQLServiceConfig:
    """mta-system settings for the database service"""

    # PostgreSQL to store data
    POSTGRESQL_DB_HOST = os.environ.get("POSTGRESQL_DB_HOST") or "localhost"
    POSTGRESQL_DB_HOST_PORT = os.environ.get("POSTGRESQL_DB_HOST_PORT") or "5432"
    POSTGRESQL_DB_NAME = os.environ.get("POSTGRESQL_DB_NAME") or "postgres"
    POSTGRESQL_ADMIN_USER = os.environ.get("POSTGRESQL_ADMIN_USER") or "postgres"
    POSTGRESQL_ADMIN_PASSWORD = (
        os.environ.get("POSTGRESQL_ADMIN_PASSWORD") or "postgres"
    )

    # demo database
    POSTGRESQL_DEMO_DB = os.environ.get("POSTGRESQL_DEMO_DB") or "db_demo"
    POSTGRESQL_DEMO_USER = os.environ.get("POSTGRESQL_DEMO_USER") or "db_user_demo"
    POSTGRESQL_DEMO_PASSWORD = os.environ.get("POSTGRESQL_DEMO_PASSWORD") or "postgres"

    POSTGRESQL_DEMO_USER_READONLY = (
        os.environ.get("POSTGRESQL_DEMO_USER_READONLY") or "db_user_demo_ro"
    )
    POSTGRESQL_DEMO_USER_READONLY_PASSWORD = (
        os.environ.get("POSTGRESQL_DEMO_USER_READONLY_PASSWORD") or "postgres"
    )


class MariaDBConfig:
    """mta-system settings for the MariaDB database"""

    # MariaDB to store data
    MARIADB_DB_HOST = os.environ.get("MARIADB_DB_HOST") or "localhost"
    MARIADB_DB_HOST_PORT = os.environ.get("MARIADB_DB_HOST_PORT") or "3306"
    MARIADB_ADMIN_USER = os.environ.get("MARIADB_ADMIN_USER") or "mariadb"
    MARIADB_ADMIN_PASSWORD = os.environ.get("MARIADB_ADMIN_PASSWORD") or "mariadb"


class OpenRefineService:

    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    NGINX_BASIC_AUTH_DIR = os.path.join(
        BASEDIR, os.environ.get("NGINX_BASIC_AUTH_DIR") or ".htpasswd_nginx"
    )
    NGINX_BASIC_AUTH_DIR_ABSOLUTE = os.path.join(
        os.environ.get("NGINX_BASIC_AUTH_DIR_ABSOLUTE") or NGINX_BASIC_AUTH_DIR
    )
    os.environ["NGINX_BASIC_AUTH_DIR"] = NGINX_BASIC_AUTH_DIR
    os.environ["NGINX_BASIC_AUTH_DIR_ABSOLUTE"] = NGINX_BASIC_AUTH_DIR_ABSOLUTE

    if not os.path.exists(NGINX_BASIC_AUTH_DIR):
        os.makedirs(NGINX_BASIC_AUTH_DIR)


class WordPressService:

    # WORDPRESS_DATA_DIR = '.wordpress'
    # if not os.path.exists(WORDPRESS_DATA_DIR):
    #     os.makedirs(WORDPRESS_DATA_DIR)

    # for i in range(7000, 7100):
    #     _temp_dir = os.path.join(WORDPRESS_DATA_DIR, str(i))
    #     if not os.path.exists(_temp_dir):
    #         os.makedirs(_temp_dir)
    pass


class BaseAppConfigsLists:
    if os.environ.get("SYSTEM_ADMINS") is not None:
        SYSTEM_ADMINS = os.environ.get("SYSTEM_ADMINS").split(";")
    else:
        SYSTEM_ADMINS = []

    if os.environ.get("ALLOWED_FQDN_FOR_EMAILS") is not None:
        ALLOWED_FQDN_FOR_EMAILS = os.environ.get("ALLOWED_FQDN_FOR_EMAILS").split(";")
    else:
        ALLOWED_FQDN_FOR_EMAILS = []

    # Services shown on the services page, in this order.
    # Each one is rendered by its own template: app/templates/services/<name>.html
    if os.environ.get("SERVICES_UI") is not None:
        SERVICES_UI = os.environ.get("SERVICES_UI").split(";")
    else:
        SERVICES_UI = [
            "pgadmin4",
            "postgresql",
            "metabase",
            "openrefine",
            "mariadb",
            "wordpress",
            "nifi",
            "superset",
            "jupyterhub",
        ]


class BaseAppConfigs(
    EMailServerConfig,
    ServiceCreationConfig,
    PostgreSQLServiceConfig,
    OpenRefineService,
    MariaDBConfig,
    WordPressService,
    BaseAppConfigsLists,
    object,
):
    """Defines base configuration for the flask app"""

    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    print(f"{datetime.now()} Projects base dir: {BASEDIR}")

    RQ_LOGGING_FILE = os.environ.get("RQ_LOGGING_FILE") or "rq-worker.log"
    RQ_LOGGING_PATH = os.path.join(BASEDIR, ".logs", RQ_LOGGING_FILE)

    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    HASH_KEY_HIDDEN = str.encode(os.environ.get("HASH_KEY_HIDDEN"))
    HASH_KEY_LINKS = str.encode(os.environ.get("HASH_KEY_LINKS"))
    COURSE_SECURITY_CODE = os.environ.get("COURSE_SECURITY_CODE") or "CODE"
    COURSE_NAME_TITLE = os.environ.get("COURSE_NAME_TITLE") or None

    SERVER_FQDN = os.environ.get("SERVER_FQDN") or "localhost"
    NGINX_BASIC_AUTH_COMMON_DB = (
        os.environ.get("NGINX_BASIC_AUTH_COMMON_DB") or "common-basic-auth.db"
    )

    print(f"{datetime.now()} SERVER_FQDN: {SERVER_FQDN}")

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(BaseAppConfigs):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = get_connection_string()
    # SQLALCHEMY_ECHO = True


class ProductionConfig(BaseAppConfigs):
    DEBUG = False
    TEMPLATES_AUTO_RELOAD = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_DATABASE_URI = get_connection_string()
