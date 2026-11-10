import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from sys import platform

from app.services.common import (
    create_user_basic_auth_common,
    get_nginx_basic_auth_directory,
    print_msg,
)

OPENREFINE_VERSION = "3.9.5"
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK_NAME") or "mtas-network"


@dataclass
class UserDataOpenRefine:
    userName: str
    password: str


def create_user_and_docker_or(user_data, docker_port, seprated_auth_file=True):
    """Creates docker containers and super use inside for openrefine"""

    if not isinstance(user_data, UserDataOpenRefine):
        print_msg("[e] Must be UserDataOpenRefine data type")
        return False

    is_errors = create_docker_container(docker_port)
    if not is_errors:
        print_msg(f"[e] Status docker creation: {is_errors}")
        print_msg("[i] Trying anyway to create superuser")

    if not create_user_basic_auth(user_data, docker_port, seprated_auth_file):
        print_msg("[i] Basic auth user for openrefine was NOT created successfully")
        return False
    else:
        print_msg("[i] Basic auth user for openrefine was created successfully")

    return True


def create_docker_container(port):
    """Creates containers for openrefine and runs on the port given"""

    if port is None:
        return False

    try:
        # creates openrefine docker
        import docker

        client = docker.from_env()
        res = client.containers.run(
            image=f"openrefine:{OPENREFINE_VERSION}",
            detach=True,
            name=f"openrefine-{port}",
            # ports = {'3333/tcp': ('127.0.0.1', port)},
            ports={"80/tcp": ("127.0.0.1", port)},
            network=DOCKER_NETWORK,
            restart_policy={"Name": "unless-stopped", "MaximumRetryCount": 0},
        )
        print_msg(f"[i] Created container with id: {res.short_id}")
    except ImportError as ex:
        print_msg(f"[e] No module installed: docker. Exception {ex}")
        return False
    except OSError as ex:
        print_msg(f"[e] No access to docker. Exception {ex}")
        return False

    return True


def create_user_basic_auth(user_data, docker_port, seprated_auth_file, logger=None):
    """Creates initial user in openrefine"""

    NGINX_BASIC_AUTH_FILE_EXTENSION = (
        os.getenv("NGINX_BASIC_AUTH_FILE_EXTENSION") or ".htpasswd"
    )
    nginx_basic_auth_dir = get_nginx_basic_auth_directory()
    auth_file = os.path.join(nginx_basic_auth_dir, NGINX_BASIC_AUTH_FILE_EXTENSION)

    if seprated_auth_file:
        auth_file = os.path.join(
            nginx_basic_auth_dir, f"{docker_port}{NGINX_BASIC_AUTH_FILE_EXTENSION}"
        )

    return create_user_basic_auth_common(
        user_data.userName, user_data.password, auth_file
    )


def main(docker_port, user_name, password):
    """To run from command line"""

    print_msg(
        "[i] Create openrefine docker and nginx basic auth user a script approach"
    )
    or_user = UserDataOpenRefine(user_name, password)
    create_user_and_docker_or(user_data=or_user, docker_port=docker_port)


if __name__ == "__main__":
    # construct the argument parse and parse the arguments

    ap = argparse.ArgumentParser()
    ap.add_argument("-dp", "--dockerport", required=True, help="Docker port")
    ap.add_argument("-u", "--username", required=True, help="User name")
    ap.add_argument("-p", "--password", required=True, help="Password")

    args = vars(ap.parse_args())

    main(
        docker_port=args["dockerport"],
        user_name=args["username"],
        password=args["password"],
    )
