"""Logins for nginx basic auth (.htpasswd files)"""

import logging
import os

from passlib.apache import HtpasswdFile

from app.config import get_settings

logger = logging.getLogger(__name__)


def basic_auth_dir() -> str:
    directory = get_settings().nginx_basic_auth_dir
    os.makedirs(directory, exist_ok=True)
    return directory


def port_auth_file(docker_port: int) -> str:
    """File with the login for the container of one user: <port>.htpasswd"""

    extension = get_settings().nginx_basic_auth_file_extension
    return os.path.join(basic_auth_dir(), f"{docker_port}{extension}")


def common_auth_file() -> str:
    """File with the logins of all users (pgAdmin 4)"""

    return os.path.join(basic_auth_dir(), get_settings().nginx_basic_auth_common_db)


def set_basic_auth_user(user_name: str, user_password: str, auth_file: str) -> bool:
    """Adds a user to the file or changes the password of the user"""

    htpasswd = HtpasswdFile(auth_file, new=not os.path.exists(auth_file))
    existed = htpasswd.set_password(user_name, user_password)
    htpasswd.save()
    logger.info(
        "Basic auth user %s was %s in %s",
        user_name,
        "updated" if existed else "created",
        auth_file,
    )
    return True


# Results of login_state
LOGIN_OK = "OK"
LOGIN_WRONG_PASSWORD = "WRONG PASSWORD"  # nosec B105: a status label, not a password
LOGIN_MISSING = "MISSING"


def login_state(user_name: str, user_password: str, auth_file: str) -> str:
    """Checks the login of a user in the file. Returns one of the LOGIN_* values."""

    if not os.path.exists(auth_file):
        return LOGIN_MISSING
    htpasswd = HtpasswdFile(auth_file)
    if user_name not in htpasswd.users():
        return LOGIN_MISSING
    if not htpasswd.check_password(user_name, user_password):
        return LOGIN_WRONG_PASSWORD
    return LOGIN_OK


def count_logins(auth_file: str) -> int:
    if not os.path.exists(auth_file):
        return 0
    return len(HtpasswdFile(auth_file).users())
