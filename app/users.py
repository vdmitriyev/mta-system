"""Users: lookup, login data and registration"""

import logging
import time
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import provisioning
from app.config import (
    JUPYTERHUB_USER_PREFIX,
    MARIADB_DB_PREFIX,
    MARIADB_USER_PREFIX,
    METABASE_PORT_OFFSET,
    NIFI_PORT_OFFSET,
    NIFI_USER_PREFIX,
    OPENREFINE_PORT_OFFSET,
    OPENREFINE_USER_PREFIX,
    PGADMIN4_USER_PREFIX,
    POSTGRESQL_DB_PREFIX,
    POSTGRESQL_USER_PREFIX,
    WORDPRESS_PORT_OFFSET,
    WORDPRESS_USER_PREFIX,
    get_settings,
)
from app.emails import email_content, send_email
from app.models import SERVICE_MODELS, Users
from app.provisioning import email_to_tokens
from app.security import generate_pin, make_hash, random_string
from app.service_settings import creates_accounts
from app.services import docker_ctl, postgresql
from app.tasks import TaskError

logger = logging.getLogger(__name__)

# Pause between two generated accounts: each one starts containers
PAUSE_BETWEEN_ACCOUNTS_SECONDS = 3


def email_to_name(email: str) -> str:
    """Forms a name from the e-mail: <name>.<surname>@domain"""

    return " ".join(email_to_tokens(email)).title()


def generate_internal_email(user_name: str, server_fqdn: str) -> str:
    """E-mail address that is used only as a login in the services"""

    if "." not in server_fqdn:
        server_fqdn = f"{server_fqdn}.loc"
    return f"{user_name}@{server_fqdn}"


def email_hash(email: str) -> str:
    return make_hash(
        email, get_settings().hash_key_links.get_secret_value(), auth_size=32
    )


def pin_hash(pin: str) -> str:
    return make_hash(
        pin, get_settings().hash_key_links.get_secret_value(), auth_size=16
    )


def find_user_by_hash(db: Session, u_hash: str) -> Users | None:
    if not u_hash:
        return None
    return (
        db.query(Users)
        .filter(Users.url_hash == u_hash, Users.deleted.is_(False))
        .order_by(Users.created_at.desc(), Users.itid.desc())
        .first()
    )


def find_user_by_email(db: Session, email: str) -> Users | None:
    return (
        db.query(Users)
        .filter(Users.email == email, Users.deleted.is_(False))
        .order_by(Users.itid.asc())
        .first()
    )


def validate_credentials(db: Session, u_hash: str, p_hash: str) -> Users | None:
    """Gets the user with this e-mail hash and PIN hash"""

    if not u_hash or not p_hash:
        return None
    return (
        db.query(Users)
        .filter(
            Users.url_hash == u_hash,
            Users.pin_hash == p_hash,
            Users.deleted.is_(False),
            Users.active.is_(True),
        )
        .first()
    )


def is_admin(user: Users | None) -> bool:
    return user is not None and user.email in get_settings().system_admins


def course_users(db: Session) -> list:
    """Gets the users of the current course, ordered by e-mail"""

    return (
        db.query(Users)
        .filter(
            Users.deleted.is_(False),
            Users.course_code == get_settings().course_security_code,
        )
        .order_by(Users.email.asc())
        .all()
    )


def access_url(user: Users) -> str:
    """Link that logs the user in"""

    return f"{get_settings().base_url}login?uHash={user.url_hash}&pHash={user.pin_hash}"


def get_user_services(db: Session, user_id: int) -> dict:
    """Gets the accounts of a user: service name -> newest row that is not deleted"""

    services = {}
    for name, model in SERVICE_MODELS.items():
        entry = (
            db.query(model)
            .filter(model.user_id == user_id, model.deleted.is_(False))
            .order_by(model.itid.desc())
            .first()
        )
        if entry is not None:
            services[name] = entry
    return services


def container_name(service: str, entry) -> str | None:
    """Name of the Docker container of a user: <prefix><service>-<port>"""

    port = getattr(entry, f"{service}_docker_port", None)
    return docker_ctl.container_name(service, port) if port is not None else None


def postgresql_uri(entry) -> str:
    """Connection string for the PostgreSQL database of a user"""

    settings = get_settings()
    return (
        f"postgresql+psycopg2://{entry.postgresql_user}:{entry.postgresql_password}"
        f"@{settings.postgresql_db_host}:{settings.postgresql_db_host_port}"
        f"/{entry.postgresql_db}"
    )


def send_access_email(user: Users) -> bool:
    """Sends the e-mail with the login link and the PIN"""

    settings = get_settings()
    link = access_url(user)
    if settings.debug:
        logger.info("Login link of %s: %s", user.email, link)
    return send_email(
        to_email=user.email,
        subject="Registration",
        content=email_content(link=link, pin=user.pin),
        settings=settings,
    )


def is_email_in_allowed_fqdn_list(email: str, allowed_email_fqdn: list) -> bool:
    """Checks that the domain of the e-mail is allowed. An empty list allows all domains."""

    if "@" not in email:
        return False
    if not allowed_email_fqdn:
        return True
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return domain in {item.lower().lstrip("@") for item in allowed_email_fqdn}


def next_account_number(db: Session) -> int:
    """Gets the number of the next account. Names and ports of the services contain it."""

    if creates_accounts(db, "postgresql"):
        number = postgresql.next_database_number()
        if number is None:
            raise TaskError("The database service is not available. Try again later.")
        return number
    return (db.query(func.max(Users.itid)).scalar() or 0) + 1


def assign_available_account(db: Session, email: str) -> Users | None:
    """Gives a prepared account (see generate_accounts_task) to a new user"""

    user = (
        db.query(Users)
        .filter(Users.is_user_assigned.is_(False), Users.deleted.is_(False))
        .order_by(Users.itid)
        .first()
    )
    if user is None:
        return None

    user.email = email
    user.is_user_assigned = True
    user.url_hash = email_hash(email)
    db.commit()
    return user


def register_new_user(db: Session, email: str, is_assigned: bool = True) -> Users:
    """Creates a user and the accounts of the user in the services"""

    settings = get_settings()
    number = next_account_number(db)
    suffix = str(number).zfill(2)
    postgresql_user = f"{POSTGRESQL_USER_PREFIX}_{suffix}"
    password = random_string()
    pin = generate_pin()

    user = Users(
        email=email,
        internal_email=generate_internal_email(postgresql_user, settings.server_fqdn),
        url_hash=email_hash(email),
        pin=pin,
        pin_hash=pin_hash(pin),
        course_code=settings.course_security_code,
        is_user_assigned=is_assigned,
    )
    db.add(user)
    db.commit()

    wordpress_port = number + WORDPRESS_PORT_OFFSET
    steps = [
        lambda: provisioning.postgresql_service_user(
            db, user.itid, f"{POSTGRESQL_DB_PREFIX}_{suffix}", postgresql_user, password
        ),
        lambda: provisioning.pgadmin4_user(
            db, user.itid, f"{PGADMIN4_USER_PREFIX}_{suffix}", password
        ),
        lambda: provisioning.metabase_user(
            db, user.itid, user.internal_email, password, number + METABASE_PORT_OFFSET
        ),
        lambda: provisioning.openrefine_user(
            db,
            user.itid,
            f"{OPENREFINE_USER_PREFIX}_{suffix}",
            password,
            number + OPENREFINE_PORT_OFFSET,
        ),
        lambda: provisioning.jupyterhub_user(
            db, user.itid, f"{JUPYTERHUB_USER_PREFIX}_{suffix}", password
        ),
        lambda: provisioning.superset_user(
            db, user.itid, postgresql_user, password, user.internal_email
        ),
        lambda: provisioning.mariadb_user(
            db,
            user.itid,
            f"{MARIADB_DB_PREFIX}_{wordpress_port}",
            f"{MARIADB_USER_PREFIX}_{suffix}",
            password,
        ),
        lambda: provisioning.wordpress_user(
            db,
            user.itid,
            f"{WORDPRESS_USER_PREFIX}_{suffix}",
            user.internal_email,
            password,
            wordpress_port,
        ),
        lambda: provisioning.nifi_user(
            db,
            user.itid,
            f"{NIFI_USER_PREFIX}_{suffix}",
            password,
            number + NIFI_PORT_OFFSET,
        ),
    ]
    for step in steps:
        try:
            step()
        except Exception:
            # one broken service must not stop the registration
            db.rollback()
            logger.exception("A service account was not created for %s", email)

    return user


def register_user_task(db: Session, email: str) -> str:
    """Background task: registers the e-mail and sends the login data"""

    user = find_user_by_email(db, email)
    known = user is not None
    if not known:
        user = assign_available_account(db, email) or register_new_user(db, email)

    if not send_access_email(user):
        raise TaskError(
            "Your account is set up, but we could not send the e-mail with the "
            "login data. Ask your instructor for help."
        )
    if known:
        return "This e-mail is already registered. We sent the login data again."
    return "Your registration is complete. Check your e-mail for the login data."


def generate_accounts_task(db: Session, count: int) -> str:
    """Background task: prepares accounts that new users get at once"""

    for index in range(count):
        if index:
            time.sleep(PAUSE_BETWEEN_ACCOUNTS_SECONDS)
        email = f"tmp.generated{index}_{uuid.uuid4().hex[:6]}@localhost.lc"
        register_new_user(db, email, is_assigned=False)
    return f"Prepared accounts: {count}"
