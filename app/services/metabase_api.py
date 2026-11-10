import argparse
import os
import time
from dataclasses import dataclass
from datetime import datetime

import requests

METABASE_VERSION = "v0.57.3"
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK_NAME") or "mtas-network"

flask_logger = None
try:
    from flask import current_app

    flask_logger = current_app.logger
except:
    pass


@dataclass
class UserDataMetabase:
    fname: str
    lname: str
    email: str
    password: str


def print_msg(msg, logger=None):
    """Prints a message into console and log (if needed)"""

    if logger is not None:
        logger.info(msg)
    elif flask_logger is not None:
        flask_logger.debug(msg)

    print(f"{datetime.now()}  {__name__}  {msg}")


def create_user_and_docker_mb(user_data, docker_port, create_user_only=False):
    """Creates docker containers and super use inside for metabase"""

    if not isinstance(user_data, UserDataMetabase):
        print_msg("[e] Must be UserDataMetabase data type")
        return False

    if not create_user_only:
        is_errors = create_docker_container(docker_port)
        if not is_errors:
            print_msg(f"[e] Status docker creation: {is_errors}")
            print_msg("[i] Trying anyway to create superuser")
    else:
        print_msg(
            f'[i] Docker container will not be created, because "create_user_only" flag was set to: {create_user_only}'
        )

    if not run_create_user(user_data, docker_port):
        return False

    return True


def create_docker_container(port: int) -> bool:
    """Creates containers for metabase and runs on the port given"""

    if port is None:
        return False

    try:
        # creates metabase docker
        import docker

        client = docker.from_env()
        res = client.containers.run(
            image=f"metabase/metabase:{METABASE_VERSION}",
            detach=True,
            name=f"metabase-{port}",
            ports={"80/tcp": ("127.0.0.1", port)},
            network=DOCKER_NETWORK,
            restart_policy={"Name": "unless-stopped", "MaximumRetryCount": 0},
            environment={"MB_JETTY_PORT": 80},
        )
        print_msg(f"[i] Created container with id: {res.short_id}")
    except ImportError as ex:
        print_msg(f"[e] No module installed: docker. Exception {ex}")
        return False
    except OSError as ex:
        print_msg(f"[e] No access to docker. Exception {ex}")
        return False

    return True


def run_create_user(user_data, port):
    """Creates user inside started container"""

    METABASE_BASE_URL = os.environ.get("METABASE_BASE_URL") or "http://localhost"
    METABASE_TRY_COUNT = os.environ.get("METABASE_TRY_COUNT") or 3
    METABASE_TRY_SLEEP_SEC = os.environ.get("METABASE_TRY_SLEEP_SEC") or 30

    if METABASE_BASE_URL == "http://localhost":
        base_url = f"{METABASE_BASE_URL}:{str(port)}"
    else:
        base_url = f"{METABASE_BASE_URL}{str(port)}"

    setup_token = None

    # tries and wait until docker container really starts
    for index, _ in enumerate(range(int(METABASE_TRY_COUNT))):
        print_msg(
            f"[i] Sleep for {METABASE_TRY_SLEEP_SEC} seconds. Re-try number: {index}"
        )
        time.sleep(int(METABASE_TRY_SLEEP_SEC))
        setup_token = get_setup_token(base_url)
        if setup_token is not None:
            break

    if setup_token is not None:
        print_msg(f"[i] Found setup-token: {setup_token}")
        if create_initialuser(base_url, user_data, setup_token):
            print_msg(
                "[i] Initial user / superuser in metabase was created successfully"
            )
            return True
        else:
            print_msg("[i] Initial user / superuser in metabase was NOT created")
    else:
        print_msg('[e] no "setup-token" found')

    return False


def get_setup_token(base_url):
    """Gets setup-token"""
    try:
        request_url = base_url + "/api/session/properties"
        print(request_url)
        res = requests.get(request_url, verify=False)
        print_msg(f"[i] Response status: {res.status_code}")
        json_data = res.json()
        return json_data["setup-token"]
    except Exception as ex:
        print_msg("[e] Exception (GET): {0}".format(ex))
        return None


def create_initialuser(base_url, user_data, setup_token, logger=None):
    """Creates initial user in metabase"""

    url = base_url + "/api/setup"
    print(url)
    payload_setup = {}
    payload_setup["token"] = setup_token
    payload_setup["prefs"] = {}
    payload_setup["prefs"]["site_name"] = "Teaching Course"
    payload_setup["prefs"]["site_locale"] = "en"
    payload_setup["prefs"]["allow_tracking"] = "false"
    payload_setup["database"] = ""
    payload_setup["invite"] = ""
    payload_setup["user"] = {}
    payload_setup["user"]["first_name"] = user_data.fname
    payload_setup["user"]["last_name"] = user_data.lname
    payload_setup["user"]["email"] = user_data.email
    payload_setup["user"]["password"] = user_data.password
    payload_setup["user"]["password_confirm"] = user_data.password
    payload_setup["user"]["site_name"] = "Teaching Course"

    try:
        res = requests.post(url, json=payload_setup, timeout=60, verify=False)
        print_msg(f"[i] Response status: {res.status_code}")
        if res.status_code == 200:
            return True
        else:
            print_msg(f"[i] Response content: {res.content}")
            print_msg(payload_setup)

    except Exception as ex:
        print_msg("[e] Exception (POST): {0}".format(ex))

    return False


def main(docker_port, fname, lname, email, password):
    """To test from command line"""

    print_msg("[i] Create metabase docker and user inside it using a script approach")
    mb_user = UserDataMetabase(fname, lname, email, password)
    create_user_and_docker_mb(
        user_data=mb_user, docker_port=docker_port, create_user_only=True
    )


if __name__ == "__main__":
    # construct the argument parse and parse the arguments

    ap = argparse.ArgumentParser()
    ap.add_argument("-dp", "--dockerport", required=True, help="Docker port")
    ap.add_argument("-f", "--fname", required=True, help="First name")
    ap.add_argument("-l", "--lname", required=True, help="Last name")
    ap.add_argument("-e", "--email", required=True, help="email")
    ap.add_argument("-p", "--password", required=True, help="password")

    args = vars(ap.parse_args())

    main(
        docker_port=args["dockerport"],
        fname=args["fname"],
        lname=args["lname"],
        email=args["email"],
        password=args["password"],
    )
