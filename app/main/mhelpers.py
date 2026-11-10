import traceback
from typing import Tuple

from flask import current_app
from sqlalchemy import and_

from ..emailsrv.pyemail import email_content, send_email
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
    Users,
    WordpressService,
)
from ..utils.uhelpers import to_json_sqla


def construct_db_uri_for_user(pg_user_data: dict) -> str:
    """Constructs DB URI for particular user.

    Args:
        pg_user_data (dict): dict with the PostgreSQL user data

    Returns:
        str: database connection string
    """

    uri_tpl = "postgresql://{db_user}:{db_password}@{db_backend}/{db_name}"
    uri_sqlalchermy = uri_tpl.format(
        db_user=pg_user_data["postgresql_user"],
        db_password=pg_user_data["postgresql_password"],
        db_name=pg_user_data["postgresql_db"],
        db_backend=current_app.config["POSTGRESQL_DB_HOST"],
    )
    return uri_sqlalchermy


def resend_email(user_data: dict, base_url: str):
    """Re-sends an email, if user already had been registered.

    Args:
        user_data (dict): user data to be use in the e-mail
        base_url (str): base URL for the link
    """

    email = user_data["email"]
    user_hash = user_data["url_hash"]
    pin = user_data["pin"]
    pin_hash = user_data["pin_hash"]
    email_body = email_content(
        link="{0}{1}?uHash={2}&pHash={3}".format(
            base_url, "login", user_hash, pin_hash
        ),
        pin=pin,
    )
    send_email(
        to_email=email,
        subject="Registration",
        content=email_body,
        settings=current_app.config,
    )


def container_status_to_html(current_status: str) -> str:
    """Presents given status as HTML.

    Args:
        current_status (str): status of the Docker container

    Returns:
        str: HTML representation of the Docker status
    """

    container_status = """<span class="badge badge-secondary">Unknown</span>"""
    if str(current_status) == "running":
        container_status = """<span class="badge badge-success">running</span>"""
    if str(current_status) == "exited":
        container_status = """<span class="badge badge-danger">exited</span>"""

    return container_status


def email_to_tokens(email: str) -> list:
    """Fetches name as tokens from the email: <name>.<surname>@domain.

    Args:
        email (str): e-mail address

    Returns:
        list: contains tokens (part of the names) from the e-mail
    """

    tokens = email[: email.find("@")].split(".")
    for _ in range(len(tokens), 2):
        tokens.append("Unknown")

    return tokens


def email_to_name(email: str) -> str:
    """Forms a proper name from the email: <name>.<surname>@domain.

    Args:
        email (str): e-mail address

    Returns:
        str: full name extracted from the e-mail address
    """

    tokens = email_to_tokens(email)
    return " ".join(tokens).title()


def generate_internal_email_based_on_existing(email: str, server_fqdn: str) -> str:
    """Generates emails for internal usage

    Args:
        email (str): email of the user
        server_fqdn (str): Server FQDN (or any string)

    Returns:
        str: newly generated email
    """

    return f"{email[:email.find('@')]}@{server_fqdn}"


def generate_internal_email(user_name: str, server_fqdn: str) -> str:
    """Generates emails for internal usage

    Args:
        email (str): email of the user
        server_fqdn (str): Server FQDN (or any string)

    Returns:
        str: newly generated email
    """

    if "." not in server_fqdn:
        server_fqdn = f"{server_fqdn}.loc"

    return f"{user_name}@{server_fqdn}"


def get_user_data(u_hash: str) -> dict:
    """Gets user data from a database.

    Args:
        u_hash (str): hashed url

    Returns:
        dict: data structure with the user data + other data to the services
    """

    user_only = get_user_data_simplified(u_hash)
    user_id = None
    if "itid" in user_only:
        user_id = user_only["itid"]

    user_data_rows = None
    if user_id is not None:
        user_data_rows = (
            db.session.query(
                Users,
                PostgreSQLService,
                PGAdmin4Service,
                MetabaseService,
                OpenRefineService,
                JupyterHubService,
                MariaDBService,
                WordpressService,
                NiFiService,
            )
            .outerjoin(PostgreSQLService)
            .outerjoin(PGAdmin4Service)
            .outerjoin(MetabaseService)
            .outerjoin(MariaDBService)
            .outerjoin(WordpressService)
            .outerjoin(OpenRefineService)
            .outerjoin(JupyterHubService)
            .outerjoin(NiFiService)
            .filter(Users.itid == user_id)
            .limit(1)
            .all()
        )

    user_data = {}
    if user_data_rows is None:
        current_app.logger.warning(f"Not user found for hash: {u_hash}")
        return user_data

    # checks are useless because of the SQL limit, but let's keep for a while
    if len(user_data_rows) == 0:
        current_app.logger.warning(f"Not user found for hash: {u_hash}")
        return user_data

    if len(user_data_rows) > 1:
        current_app.logger.warning(
            f"More users that expected were found for hash: {u_hash}"
        )
        return user_data

    if len(user_data_rows) == 1:
        col_ignore = []
        # col_ignore = ['itid', 'deleted', 'created_at']
        for table_el in user_data_rows[0]:
            if table_el is not None:
                user_data[table_el.__tablename__] = {}
                for col in table_el.__table__.columns:
                    if col.name not in col_ignore:
                        user_data[table_el.__tablename__][col.name] = table_el[col.name]

    return user_data


def get_user_data_simplified(u_hash: str) -> dict:
    """Gets user data from a database - simplified version.

    Args:
        u_hash (str): hashed url

    Returns:
        dict: data structure with the user data
    """

    user_data_rows = (
        db.session.query(Users)
        .filter(and_(Users.url_hash == u_hash, Users.deleted == False))
        .order_by(Users.created_at.desc())
        .limit(1)
        .all()
    )

    user_data = {}

    # checks are useless because of the SQL limit, but let's keep for a while
    if len(user_data_rows) == 0:
        current_app.logger.warning(f"Not user found for hash: {u_hash}")
        return user_data

    if len(user_data_rows) > 1:
        current_app.logger.warning(
            f"More users then expected were found for bash: {u_hash}"
        )
        return user_data

    if len(user_data_rows) == 1:
        user_data = to_json_sqla(user_data_rows[0])

    return user_data


def user_containers_status(user_data: dict) -> Tuple[str, str, str]:
    """Gets docker container status of a user.

    Args:
        user_data (dict): user data

    Returns:
        Tuple[str, str, str]: status of Docker container as HTML for metabase, openrefine, nifi services
    """
    _statuses = {
        "metabase": '<span class="badge badge-secondary">Unknown</span>',
        "openrefine": '<span class="badge badge-secondary">Unknown</span>',
        "nifi": '<span class="badge badge-secondary">Unknown</span>',
        "wordpress": '<span class="badge badge-secondary">Unknown</span>',
    }
    try:
        import docker

        client = docker.from_env()

        for service_name in _statuses:
            try:
                _container = None
                if f"{service_name}_service" in user_data:
                    _container_name = f'{service_name}-{user_data[f"{service_name}_service"][f"{service_name}_docker_port"]}'
                    _container = client.containers.get(_container_name)
                else:
                    current_app.logger.warning(
                        f"No user data on container of the service: {service_name}"
                    )

                if _container is not None:
                    _statuses[service_name] = container_status_to_html(
                        _container.status
                    )
            except Exception as ex:
                current_app.logger.error(
                    f"Error in fetching container data for service: {service_name}"
                )
                current_app.logger.error(traceback.format_exc())
    except ImportError as ex:
        current_app.logger.error(f"No module installed: docker. Exception {ex}")
        return _statuses
    except OSError as ex:
        current_app.logger.error(f"No access to docker. Exception {ex}")
        return _statuses
    except Exception as ex:
        current_app.logger.error(traceback.format_exc())
        return _statuses
    return _statuses


def start_docker_container(user_data: dict, service_type: str) -> str:
    """Starts a docker container.

    Args:
        user_data (dict): a user data
        service_type (str): service type to be started

    Returns:
        str: message after the start
    """

    message = None
    try:
        import docker

        client = docker.from_env()
        docker_port = user_data[f"{service_type}_docker_port"]
        container_name = f"{service_type}-{docker_port}"
        current_app.logger.debug(f"Start container: {container_name}")
        docker_container = client.containers.get(container_name)
        if docker_container is not None:
            docker_container.start()
            message = "[i] Service should be running. Be patient, the process may take a while"
        else:
            message = "[x] This service was not found"
    except Exception as ex:
        current_app.logger.error(traceback.format_exc())
        message = f"[e] Exception happened"

    return message


def read_file(filename: str) -> str:
    """Reads a file

    Args:
        filename (str): name of the file to read

    Returns:
        str: content of the file
    """

    f_content = None
    with open(filename, "r") as _f:
        f_content = _f.read()
    return f_content


def enable_logging_for_sqlalchemy_queries():
    """Enabled logging for SQL queries run with SQLAlchemy"""
    import logging

    logging.basicConfig()
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)


def disable_logging_for_sqlalchemy_queries():
    """Disable logging for SQL queries run with SQLAlchemy"""
    import logging

    logging.basicConfig()
    logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
