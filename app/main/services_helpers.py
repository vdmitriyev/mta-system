import os
import pathlib
import traceback

from flask import current_app

from ..extensions import db
from ..models import (
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
from ..services.metabase_api import UserDataMetabase, create_user_and_docker_mb
from ..services.nifi_api import UserDataNiFi, create_user_and_docker_nifi
from ..services.openrefine_api import UserDataOpenRefine, create_user_and_docker_or
from ..services.pgadmin4_api import new_user_pgadmin4, new_user_pgadmin4_for_web_auth
from ..services.superset_api import SupersetAPIClient, SupersetUser
from ..services.wordpress_api import UserDataWordpress, create_user_and_docker_wordpress
from .mariadb_helpers import create_mariadb_db
from .mhelpers import email_to_tokens
from .postgresql_helpers import create_postgresql_db


def postgresql_service_user(user_id: int, db_name: str, db_user: str, db_password: str):

    if not current_app.config["CREATE_POSTGRESQL_SERVICE"]:
        current_app.logger.warning(
            f"postgresql_service user will NOT be created. Creation of postgresql_service disabled. DB user: {db_user}"
        )
        return False

    is_created = create_postgresql_db(
        db_name=db_name, db_user=db_user, db_password=db_password
    )

    _db_entry = PostgreSQLService(
        user_id=user_id,
        postgresql_db=db_name,
        postgresql_user=db_user,
        postgresql_password=db_password,
        created=is_created,
    )
    db.session.add(_db_entry)
    db.session.commit()

    if is_created:
        current_app.logger.info(
            f"User and database in PostgreSQL were created. DB user: {db_user}"
        )
    else:
        current_app.logger.warning(
            f"User and database in PostgreSQL were NOT created. DB user: {db_user}"
        )


def pgadmin4_user(
    user_id: int, user_name: str, password: str, email: str = None
) -> None:
    """Creates PGAdmin4 user"""

    if not current_app.config["CREATE_PG4ADMIN_SERVICE"]:
        current_app.logger.warning(
            f"pgadmin4_service user will NOT be created. Creation of pgadmin4_service disabled. Internal e-mail: {email}"
        )
        return False

    is_created = _pgadmin4_api_via_web(user_name, password)

    _db_entry = PGAdmin4Service(
        user_id=user_id,
        pgadmin4_user=user_name,
        pgadmin4_password=password,
        created=is_created,
    )
    db.session.add(_db_entry)
    db.session.commit()

    if is_created:
        current_app.logger.warning(f"PGAdmin4 user was created. Name: {user_name}")
    else:
        current_app.logger.warning(f"PGAdmin4 user was NOT created. Name: {user_name}")


def _pgadmin4_api_via_web(new_user_name, new_pgadmin4_password):
    """Uses webserver approach that makes use of basic auth method in pgadmin4"""
    return new_user_pgadmin4_for_web_auth(new_user_name, new_pgadmin4_password)


def jupyterhub_user(user_id, jupyterhub_user, jupyterhub_password):

    if not current_app.config["CREATE_JUPYTERHUB_SERVICE"]:
        current_app.logger.warning(
            f"jupyterhub_service user will NOT be created. It was disabled. JupyterHub user: {jupyterhub_user}"
        )
        return False

    _db_entry = JupyterHubService(
        user_id=user_id,
        jupyterhub_user=jupyterhub_user,
        jupyterhub_password=jupyterhub_password,
        created=False,
    )
    db.session.add(_db_entry)
    db.session.commit()


def metabase_user(user_id: int, email: str, password: str, docker_port: int):
    """Creates metabase user and docker container"""

    current_app.logger.debug(f"metabase docker port should be: {docker_port}")

    if not current_app.config["CREATE_METABASE_SERVICE"]:
        current_app.logger.warning(
            f"metabase_service user will NOT be created. It was disabled. Internal e-mail: {email}"
        )
        return False

    tokens = email_to_tokens(email)

    mb_user = UserDataMetabase(
        fname=tokens[0].title(), lname=tokens[1].title(), email=email, password=password
    )

    is_created = create_user_and_docker_mb(user_data=mb_user, docker_port=docker_port)

    _db_entry = MetabaseService(
        user_id=user_id,
        metabase_login=email,
        metabase_password=password,
        metabase_docker_port=docker_port,
        created=is_created,
    )
    db.session.add(_db_entry)
    db.session.commit()

    if is_created:
        current_app.logger.info(
            f"metabase docker and user were created successfully. Internal email: {email}"
        )
    else:
        current_app.logger.warning(
            f"metabase docker and user were NOT successfully created. Internal email: {email}"
        )
    return is_created


def openrefine_user(
    user_id: int,
    user_name: str,
    password: str,
    docker_port: int,
    force_create: bool = False,
):
    """Creates openrefine user and docker container"""

    if not force_create:
        if not current_app.config["CREATE_OPENREFINE_SERVICE"]:
            current_app.logger.warning(
                f"openrefine_service user will NOT be created. It was disabled. User name: {user_name}"
            )
            return False
    else:
        current_app.logger.warning(
            f'openrefine_service user will be created with "force_create={force_create}" option. User name: {user_name}'
        )

    or_user = UserDataOpenRefine(userName=user_name, password=password)

    is_created = create_user_and_docker_or(user_data=or_user, docker_port=docker_port)
    _db_entry = OpenRefineService(
        user_id=user_id,
        openrefine_user=user_name,
        openrefine_password=password,
        openrefine_docker_port=docker_port,
        created=is_created,
    )
    db.session.add(_db_entry)
    db.session.commit()

    if is_created:
        current_app.logger.info(
            f"openrefine docker and user were created successfully. User: {user_name}"
        )
    else:
        current_app.logger.warning(
            f"openrefine docker and user were NOT successfully created. User: {user_name}"
        )


def mariadb_user(user_id: int, db_name: str, db_user: str, db_password: str):

    if not current_app.config["CREATE_MARIADB_SERVICE"]:
        current_app.logger.warning(
            f"mariadb_service user will NOT be created. Creation of mariadb_service disabled. DB user: {db_user}"
        )
        return False

    is_created = create_mariadb_db(
        db_name=db_name, db_user=db_user, db_password=db_password
    )

    _db_entry = MariaDBService(
        user_id=user_id,
        mariadb_db=db_name,
        mariadb_user=db_user,
        mariadb_password=db_password,
        created=is_created,
    )
    db.session.add(_db_entry)
    db.session.commit()

    if is_created:
        current_app.logger.info(
            f"User and database in MariaDB were created. DB user: {db_user}"
        )
    else:
        current_app.logger.warning(
            f"User and database in MariaDB were NOT created. DB user: {db_user}"
        )


def wordpress_user(
    user_id: int,
    user_name: str,
    user_email: str,
    password: str,
    docker_port: int,
    wordpress_base_url: str,
    force_create: bool = False,
):
    """Creates wordpress user and docker container"""

    if not force_create:
        if not current_app.config["CREATE_WORDPRESS_SERVICE"]:
            current_app.logger.warning(
                f"wordpress_service user will NOT be created. It was disabled. User name: {user_name}"
            )
            return False
    else:
        current_app.logger.warning(
            f'wordpress_service user will be created with "force_create={force_create}" option. User name: {user_name}'
        )

    _db_entry_mariadb = (
        db.session.query(MariaDBService)
        .filter(MariaDBService.user_id == user_id)
        .limit(1)
        .all()
    )
    is_created = False

    if len(_db_entry_mariadb) > 0:
        _mariadb_user_data = _db_entry_mariadb[0]
        wp_user = UserDataWordpress(
            wpLogin=user_name,
            wpPassword=password,
            wpEmail=user_email,
            databaseHost=current_app.config["MARIADB_DB_HOST"],
            databaseName=_mariadb_user_data["mariadb_db"],
            databaseUser=_mariadb_user_data["mariadb_user"],
            databasePassword=_mariadb_user_data["mariadb_password"],
            wordpressBaseURL=wordpress_base_url,
        )

        # is_created = create_user_and_docker_wordpress(user_data = wp_user, docker_port = docker_port)
        with current_app.app_context():
            from ..extensions import rq_worker

            wp_job = rq_worker.enqueue(
                create_user_and_docker_wordpress,
                user_data=wp_user,
                docker_port=docker_port,
                logger_path=current_app.config["RQ_LOGGING_PATH"],
            )

            current_app.logger.debug(
                f"Create wordpress service using rq job: {wp_job.id}. User: {user_name}"
            )

        _db_entry = WordpressService(
            user_id=user_id,
            wordpress_login=user_name,
            wordpress_password=password,
            wordpress_docker_port=docker_port,
            created=is_created,
        )
        db.session.add(_db_entry)
        db.session.commit()
    else:
        current_app.logger.error(
            f"Not MariaDB database was found for the user_id: {user_id}. User: {user_name}"
        )

    current_app.logger.info(
        f"wordpress docker and user should be created by RQ job. User: {user_name}"
    )

    # if is_created:
    #     current_app.logger.info(f'wordpress docker and user were created successfully. User: {user_name}')
    # else:
    #     current_app.logger.warning(f'wordpress docker and user were NOT created. User: {user_name}')


def nifi_user(user_id: int, user_name: str, password: str, docker_port: int) -> None:
    """Creates nifi user and docker container"""

    if not current_app.config["CREATE_NIFI_SERVICE"]:
        current_app.logger.warning(
            f"nifi_service user will NOT be created. It was disabled. User name: {user_name}"
        )
        return False

    nifi_user = UserDataNiFi(userName=user_name, password=password)
    is_created = create_user_and_docker_nifi(
        user_data=nifi_user, docker_port=docker_port
    )

    _db_entry = NiFiService(
        user_id=user_id,
        nifi_user=user_name,
        nifi_password=password,
        nifi_docker_port=docker_port,
        created=is_created,
    )
    db.session.add(_db_entry)
    db.session.commit()

    if is_created:
        current_app.logger.info(
            f"NiFi docker and user were created successfully. User: {user_name}"
        )
    else:
        current_app.logger.warning(
            f"NiFi docker and user were NOT successfully created. User: {user_name}"
        )


def superset_user(user_id: int, login: str, password: str, email: str) -> None:
    """Creates superset user and also

    Args:
        user_id (int): ID of the user associated with the superset service
        login (str): login to be use in superset
        password (str): password to be use in superset
        email (str): _description_
    """

    try:

        if not current_app.config["CREATE_SUPERSET_SERVICE"]:
            current_app.logger.warning(
                f"superset_service user will NOT be created. It was disabled. Internal e-mail: {email}"
            )
            return False

        obj = SupersetAPIClient(
            SupersetUser(login=login, password=password, email=email)
        )
        is_created = obj.create_new_user()
        superset_db_entry = SupersetService(
            user_id=user_id,
            superset_user=login,
            superset_password=password,
            created=is_created,
        )
        db.session.add(superset_db_entry)
        db.session.commit()
        if is_created:
            current_app.logger.debug(
                f"superset user was successfully created. Internal e-mail: {email}"
            )
        else:
            current_app.logger.warning(
                f"superset user was NOT created. Internal e-mail: {email}"
            )

    except:
        current_app.logger.error(traceback.format_exc())
        current_app.logger.error(
            f"Was not able to create user for the Superset service. Internal e-mail: {email}"
        )
