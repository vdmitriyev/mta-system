import os
from datetime import datetime

from flask import current_app
from passlib.apache import HtpasswdFile


def print_msg(msg, logger=None):
    """Prints a message into console and log (if needed)"""

    if logger is not None:
        logger.info(msg)
    print(f"{datetime.now()}  {__name__}  {msg}")

    current_app.logger.debug(f"{msg}")


def get_nginx_basic_auth_directory():

    nginx_basic_auth_dir = None
    NGINX_BASIC_AUTH_DIR_ABSOLUTE = os.getenv("NGINX_BASIC_AUTH_DIR_ABSOLUTE") or None

    nginx_basic_auth_dir = NGINX_BASIC_AUTH_DIR_ABSOLUTE
    if nginx_basic_auth_dir is None:
        nginx_basic_auth_dir = os.getenv("NGINX_BASIC_AUTH_DIR") or None

    if nginx_basic_auth_dir is None:
        nginx_basic_auth_dir = "."

    if not os.path.exists(nginx_basic_auth_dir):
        os.mkdir(nginx_basic_auth_dir)

    return nginx_basic_auth_dir


def create_user_basic_auth_common(user_name: str, user_password: str, auth_file: str):
    """Creates initial user in openrefine"""

    if not os.path.exists(auth_file):
        print_msg(f"[i] Create HtpasswdFile (basic auth) file: {auth_file}")
        ht = HtpasswdFile(auth_file, new=True)
    else:
        print_msg(f"[i] Edit HtpasswdFile (basic auth) file: {auth_file}")
        ht = HtpasswdFile(auth_file)

    user_exists = ht.set_password(user_name, user_password)
    if user_exists:
        print_msg(f"[i] Password for existing user was updated: {user_name}")
    else:
        print_msg(f"[i] New user was created: {user_name}")
    ht.save()

    return True
