import traceback

from flask import current_app

from .. import settings as settings
from ..extensions import db
from ..models import Users
from ..utils.security import generate_pin, make_hash, random_string
from ..utils.uhelpers import to_json_sqla
from .mhelpers import generate_internal_email, resend_email
from .postgresql_helpers import new_postgresql_db_names
from .services_helpers import (
    jupyterhub_user,
    mariadb_user,
    metabase_user,
    nifi_user,
    openrefine_user,
    pgadmin4_user,
    postgresql_service_user,
    superset_user,
    wordpress_user,
)


def create_new_user(
    new_user_email: str,
    new_user_internal_email: str,
    new_user_hash: str,
    new_pin: int,
    new_pin_hash: str,
    is_user_assigned: bool = True,
) -> int:
    """Creates new user in the table with users

    Args:
        new_user_email (str): email of the user
        new_user_email (str): internal email of the user
        new_user_hash (str): _description_
        new_pin (int): _description_
        new_pin_hash (str): _description_
        is_user_assigned (bool): flag to be able to create pre-created users

    Returns:
        int: ID of a newly created user
    """

    course_security_code = current_app.config["COURSE_SECURITY_CODE"]
    new_user = Users(
        email=new_user_email,
        internal_email=new_user_internal_email,
        url_hash=new_user_hash,
        pin=new_pin,
        pin_hash=new_pin_hash,
        course_code=course_security_code,
        is_user_assigned=is_user_assigned,
    )
    db.session.add(new_user)
    db.session.commit()

    latest_new_user = (
        db.session.query(Users)
        .filter(Users.email == new_user_email)
        .order_by(Users.created_at.desc())
        .all()
    )
    new_user_id = -1
    if len(latest_new_user) == 1:
        new_user_id = latest_new_user[0].itid

    return new_user_id


def is_email_in_allowed_fqdn_list(email: str, allowed_email_fqdn: list) -> bool:
    """
    Checks if the domain of the given email is in the specified list of allowed domains.

    Args:
        email (str): The email address to check.
        allowed_email_fqdn (list): A list of allowed FQDN names for email.

    Returns:
        bool: True if the domain is allowed, False otherwise.
    """

    try:
        if "@" not in email:
            return False

        if len(allowed_email_fqdn) == 0:
            current_app.logger.warning(
                "The list with allowed FQDN emails is empty, tus all domains are allowed. Skip check."
            )
            return True

        domain = email.split("@")[-1]
        if domain in allowed_email_fqdn:
            return True
    except (IndexError, ValueError):
        current_app.logger.error(traceback.format_exc())
        return False
    return False


def send_confirmation_email(email):
    """Sends confirmation e-mail to the user

    Args:
        email (_type_): email of the user
    """

    current_app.logger.info(f"Try to send confirmation e-mail to: {email}")
    email_exists_rows = db.session.query(Users).filter(Users.email == email).all()
    if len(email_exists_rows) == 1:
        user_data = to_json_sqla(email_exists_rows[0])
        resend_email(user_data=user_data, base_url=settings.BASE_URL)
    else:
        current_app.logger.info(
            f"Was not able to send confirmation email. User with such e-mail does not exist: {email}"
        )


def check_if_user_exists(email):
    """Check if user already exist

    Args:
        email (_type_): e-email exists
    """

    email_exists_rows = db.session.query(Users).filter(Users.email == email).all()
    user_data = {}
    if len(email_exists_rows) > 0:
        user_data = to_json_sqla(email_exists_rows[0])
        return True, user_data
    return False, user_data


def assign_available_account_to_user(email):
    """Assigns pre-created and free user accounts to the new users.

    Args:
        email (_type_): email of the user
    """

    is_exist, user_data = check_if_user_exists(email)
    if is_exist:
        resend_email(user_data, settings.BASE_URL)

    next_available_account = (
        db.session.query(Users)
        .filter(Users.is_user_assigned == False)
        .order_by(Users.itid)
        .limit(1)
        .all()
    )

    if len(next_available_account) == 1:
        new_user = next_available_account[0]
        new_user.email = email
        new_user.is_user_assigned = True
        new_user.url_hash = str(
            make_hash(email, current_app.config["HASH_KEY_LINKS"], AUTH_SIZE=32)
        )
        db.session.add(new_user)
        db.session.commit()
        email_assigned_to_user = (
            db.session.query(Users).filter(Users.email == email).all()
        )
        user_data = to_json_sqla(email_assigned_to_user[0])
        resend_email(user_data, settings.BASE_URL)
        return True
    else:
        current_app.logger.info(
            f"Was not able to assign new account to the user. No available accounts left for users."
        )

    return False


def register_new_routine(new_user_email: str, do_assign_user: bool = True):
    """Register a new user in the system using email from the web form

    Args:
        new_user_email (str):

    Raises:
        Exception: _description_

    Returns:
        _type_: _description_
    """

    was_registered = False
    email_exists_rows = (
        db.session.query(Users).filter(Users.email == new_user_email).all()
    )

    # check, if the new user needed
    if len(email_exists_rows) == 0:

        new_pin = generate_pin()
        new_user_password = random_string()
        # new_postgresql_password = new_user_password

        new_postgresql_db, new_postgresql_user, new_postgresql_user_order = (
            new_postgresql_db_names()
        )

        if new_postgresql_db is None or new_postgresql_user is None:
            raise Exception("Something went wrong during the database creation process")

        new_user_internal_email = generate_internal_email(
            new_postgresql_user, current_app.config["SERVER_FQDN"]
        )

        new_user_hash = str(
            make_hash(
                new_user_email, current_app.config["HASH_KEY_LINKS"], AUTH_SIZE=32
            )
        )
        new_pin_hash = str(
            make_hash(new_pin, current_app.config["HASH_KEY_LINKS"], AUTH_SIZE=16)
        )

        new_user_id = create_new_user(
            new_user_email,
            new_user_internal_email,
            new_user_hash,
            new_pin,
            new_pin_hash,
            do_assign_user,
        )

        if new_user_id != -1:

            # metabase user
            new_mb_docker_port = (
                int(new_postgresql_user_order) + settings.METABASE_PORT_OFFSET
            )

            metabase_user(
                user_id=new_user_id,
                email=new_user_internal_email,
                password=new_user_password,
                docker_port=new_mb_docker_port,
            )

            # openrefine user
            new_openrefine_user = "{0}_{1}".format(
                settings.OPENREFINE_USER_PREFIX, new_postgresql_user[-2:]
            )
            new_openrefine_docker_port = (
                int(new_postgresql_user_order) + settings.OPENREFINE_PORT_OFFSET
            )
            current_app.logger.info(
                f"openrefine docker port should be: {new_openrefine_docker_port}"
            )
            openrefine_user(
                user_id=new_user_id,
                user_name=new_openrefine_user,
                password=new_user_password,
                docker_port=new_openrefine_docker_port,
            )

            # jupyterhub user
            new_jupyterhub_user = "{0}_{1}".format(
                settings.JUPYTERHUB_USER_PREFIX, new_postgresql_user[-2:]
            )
            jupyterhub_user(
                user_id=new_user_id,
                jupyterhub_user=new_jupyterhub_user,
                jupyterhub_password=new_user_password,
            )

            # postgresql
            postgresql_service_user(
                user_id=new_user_id,
                db_name=new_postgresql_db,
                db_user=new_postgresql_user,
                db_password=new_user_password,
            )

            # PGAdmin4 user
            new_pgadmin4_user = "{0}_{1}".format(
                settings.PGADMIN4_USER_PREFIX, new_postgresql_user[-2:]
            )
            pgadmin4_user(
                user_id=new_user_id,
                user_name=new_pgadmin4_user,
                password=new_user_password,
                email=new_user_internal_email,
            )

            # superset user
            new_superset_login, new_superset_password = (
                new_postgresql_user,
                new_user_password,
            )
            superset_user(
                user_id=new_user_id,
                login=new_superset_login,
                password=new_superset_password,
                email=new_user_internal_email,
            )

            # mariadb user
            new_wordpress_docker_port = (
                int(new_postgresql_user[-2:]) + settings.WORDPRESS_PORT_OFFSET
            )
            new_mariadb_user = "{0}_{1}".format(
                settings.MARIADB_USER_PREFIX, new_postgresql_user[-2:]
            )
            new_mariadb_db = "{0}_{1}".format(
                settings.MARIADB_DB_PREFIX, new_wordpress_docker_port
            )
            mariadb_user(
                user_id=new_user_id,
                db_name=new_mariadb_db,
                db_user=new_mariadb_user,
                db_password=new_user_password,
            )

            # wordpress user
            new_wordpress_user = "{0}_{1}".format(
                settings.WORPRESS_USER_PREFIX, new_postgresql_user[-2:]
            )
            wordpress_user(
                user_id=new_user_id,
                user_name=new_wordpress_user,
                user_email=new_user_internal_email,
                password=new_user_password,
                docker_port=new_wordpress_docker_port,
                wordpress_base_url=settings.WORDPRESS_BASE_URL,
            )

            # nifi user
            new_nifi_user = "{0}_{1}".format(
                settings.NIFI_USER_PREFIX, new_postgresql_user[-2:]
            )
            new_nifi_docker_port = (
                int(new_postgresql_user_order) + settings.NIFI_PORT_OFFSET
            )
            current_app.logger.info(
                f"nifi docker port should be: {new_nifi_docker_port}"
            )
            nifi_user(
                user_id=new_user_id,
                user_name=new_nifi_user,
                password=new_user_password,
                docker_port=new_nifi_docker_port,
            )

            was_registered = True

    return was_registered
