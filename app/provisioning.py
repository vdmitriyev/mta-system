"""Creates the accounts of a user in the services and stores them in the database.

Each function returns True if the account was created. A service that is
switched off on the admin page "Auto creation" is skipped.
"""

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    JupyterHubService,
    MariaDBService,
    MetabaseService,
    NiFiService,
    OpenRefineService,
    PGAdmin4Service,
    PostgreSQLService,
    SupersetService,
    WordpressService,
)
from app.service_settings import creates_accounts
from app.services import (
    mariadb,
    metabase_api,
    nifi_api,
    openrefine_api,
    pgadmin4_api,
    postgresql,
    superset_api,
    wordpress_api,
)

logger = logging.getLogger(__name__)


def _save(db: Session, entry, name: str) -> bool:
    db.add(entry)
    db.commit()
    if entry.created:
        logger.info("%s account was created for user %s", name, entry.user_id)
    else:
        logger.warning("%s account was NOT created for user %s", name, entry.user_id)
    return entry.created


def _skip(name: str) -> bool:
    logger.info("%s is switched off: no account is created", name)
    return False


def email_to_tokens(email: str) -> list:
    """Gets the parts of the name from an e-mail: <name>.<surname>@domain"""

    tokens = email[: email.find("@")].split(".")
    while len(tokens) < 2:
        tokens.append("Unknown")
    return tokens


def postgresql_service_user(
    db: Session,
    user_id: int,
    db_name: str,
    db_user: str,
    db_password: str,
    force_create: bool = False,
) -> bool:
    if not force_create and not creates_accounts(db, "postgresql"):
        return _skip("PostgreSQL")

    is_created = postgresql.create_postgresql_db(db_name, db_user, db_password)
    entry = PostgreSQLService(
        user_id=user_id,
        postgresql_db=db_name,
        postgresql_user=db_user,
        postgresql_password=db_password,
        created=is_created,
    )
    return _save(db, entry, "PostgreSQL")


def pgadmin4_user(
    db: Session, user_id: int, user_name: str, password: str, force_create: bool = False
) -> bool:
    if not force_create and not creates_accounts(db, "pgadmin4"):
        return _skip("pgAdmin 4")

    is_created = pgadmin4_api.new_user_pgadmin4_for_web_auth(user_name, password)
    entry = PGAdmin4Service(
        user_id=user_id,
        pgadmin4_user=user_name,
        pgadmin4_password=password,
        created=is_created,
    )
    return _save(db, entry, "pgAdmin 4")


def jupyterhub_user(db: Session, user_id: int, user_name: str, password: str) -> bool:
    """Stores the JupyterHub login. An admin creates the account in JupyterHub."""

    if not creates_accounts(db, "jupyterhub"):
        return _skip("JupyterHub")

    entry = JupyterHubService(
        user_id=user_id,
        jupyterhub_user=user_name,
        jupyterhub_password=password,
        created=False,
    )
    db.add(entry)
    db.commit()
    return True


def metabase_user(
    db: Session,
    user_id: int,
    email: str,
    password: str,
    docker_port: int,
    force_create: bool = False,
) -> bool:
    if not force_create and not creates_accounts(db, "metabase"):
        return _skip("Metabase")

    tokens = email_to_tokens(email)
    is_created = metabase_api.create_user_and_docker_mb(
        metabase_api.UserDataMetabase(
            fname=tokens[0].title(),
            lname=tokens[1].title(),
            email=email,
            password=password,
        ),
        docker_port,
    )
    entry = MetabaseService(
        user_id=user_id,
        metabase_login=email,
        metabase_password=password,
        metabase_docker_port=docker_port,
        created=is_created,
    )
    return _save(db, entry, "Metabase")


def openrefine_user(
    db: Session,
    user_id: int,
    user_name: str,
    password: str,
    docker_port: int,
    force_create: bool = False,
) -> bool:
    if not force_create and not creates_accounts(db, "openrefine"):
        return _skip("OpenRefine")

    is_created = openrefine_api.create_user_and_docker_or(
        openrefine_api.UserDataOpenRefine(userName=user_name, password=password),
        docker_port,
    )
    entry = OpenRefineService(
        user_id=user_id,
        openrefine_user=user_name,
        openrefine_password=password,
        openrefine_docker_port=docker_port,
        created=is_created,
    )
    return _save(db, entry, "OpenRefine")


def mariadb_user(
    db: Session, user_id: int, db_name: str, db_user: str, db_password: str
) -> bool:
    if not creates_accounts(db, "mariadb"):
        return _skip("MariaDB")

    is_created = mariadb.create_mariadb_db(db_name, db_user, db_password)
    entry = MariaDBService(
        user_id=user_id,
        mariadb_db=db_name,
        mariadb_user=db_user,
        mariadb_password=db_password,
        created=is_created,
    )
    return _save(db, entry, "MariaDB")


def wordpress_user(
    db: Session,
    user_id: int,
    user_name: str,
    user_email: str,
    password: str,
    docker_port: int,
) -> bool:
    """Creates the WordPress container of a user. Needs the MariaDB database of the user."""

    settings = get_settings()
    if not creates_accounts(db, "wordpress"):
        return _skip("WordPress")

    mariadb_entry = (
        db.query(MariaDBService)
        .filter(MariaDBService.user_id == user_id, MariaDBService.deleted.is_(False))
        .order_by(MariaDBService.itid.desc())
        .first()
    )
    if mariadb_entry is None:
        logger.error("No MariaDB database for user %s: no WordPress", user_id)
        return False

    is_created = wordpress_api.create_user_and_docker_wordpress(
        wordpress_api.UserDataWordpress(
            wpLogin=user_name,
            wpPassword=password,
            wpEmail=user_email,
            databaseHost=settings.mariadb_db_host,
            databaseName=mariadb_entry.mariadb_db,
            databaseUser=mariadb_entry.mariadb_user,
            databasePassword=mariadb_entry.mariadb_password,
            wordpressBaseURL=settings.wordpress_base_url,
        ),
        docker_port,
    )
    entry = WordpressService(
        user_id=user_id,
        wordpress_login=user_name,
        wordpress_password=password,
        wordpress_docker_port=docker_port,
        created=is_created,
    )
    return _save(db, entry, "WordPress")


def nifi_user(
    db: Session, user_id: int, user_name: str, password: str, docker_port: int
) -> bool:
    if not creates_accounts(db, "nifi"):
        return _skip("NiFi")

    is_created = nifi_api.create_user_and_docker_nifi(
        nifi_api.UserDataNiFi(userName=user_name, password=password), docker_port
    )
    entry = NiFiService(
        user_id=user_id,
        nifi_user=user_name,
        nifi_password=password,
        nifi_docker_port=docker_port,
        created=is_created,
    )
    return _save(db, entry, "NiFi")


def superset_user(
    db: Session, user_id: int, login: str, password: str, email: str
) -> bool:
    if not creates_accounts(db, "superset"):
        return _skip("Superset")

    client = superset_api.SupersetAPIClient(
        superset_api.SupersetUser(login=login, password=password, email=email)
    )
    entry = SupersetService(
        user_id=user_id,
        superset_user=login,
        superset_password=password,
        created=client.create_new_user(),
    )
    return _save(db, entry, "Superset")
