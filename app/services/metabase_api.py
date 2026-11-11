import logging
import time
from dataclasses import dataclass

import requests

from app.config import get_settings
from app.services import docker_ctl

METABASE_VERSION = "v0.57.3"
IMAGE = f"metabase/metabase:{METABASE_VERSION}"
IMAGE_HINT = "Download it on the server:"
IMAGE_COMMAND = f"docker pull {IMAGE}"

logger = logging.getLogger(__name__)


@dataclass
class UserDataMetabase:
    fname: str
    lname: str
    email: str
    password: str


def create_user_and_docker_mb(user_data: UserDataMetabase, docker_port: int) -> bool:
    """Creates the Metabase container of a user and the first user (admin) in it"""

    image = check_image()
    if not image.ok:
        logger.error("Metabase is not created: %s", image.text)
        return False
    if not create_docker_container(docker_port):
        logger.warning("Metabase container was not created. Try to create the user.")
    return run_create_user(user_data, docker_port)


def check_image(ask_registry: bool = True) -> docker_ctl.ImageCheck:
    return docker_ctl.check_image(IMAGE, ask_registry, IMAGE_HINT, IMAGE_COMMAND)


def create_docker_container(port: int) -> bool:
    if port is None:
        return False
    try:
        container = docker_ctl.get_client().containers.run(
            image=IMAGE,
            detach=True,
            name=f"metabase-{port}",
            ports={"80/tcp": ("127.0.0.1", port)},
            network=get_settings().docker_network_name,
            restart_policy={"Name": "unless-stopped", "MaximumRetryCount": 0},
            environment={"MB_JETTY_PORT": 80},
        )
        logger.info("Created Metabase container: %s", container.short_id)
        return True
    except Exception as error:
        logger.error("Cannot create the Metabase container: %s", error)
        return False


def base_url_for(port: int) -> str:
    base_url = get_settings().metabase_base_url
    if base_url == "http://localhost":
        return f"{base_url}:{port}"
    return f"{base_url}{port}"


def run_create_user(user_data: UserDataMetabase, port: int) -> bool:
    """Waits until Metabase runs, then creates the first user"""

    settings = get_settings()
    base_url = base_url_for(port)

    setup_token = None
    for attempt in range(settings.metabase_try_count):
        logger.info("Wait for Metabase on port %s (attempt %s)", port, attempt + 1)
        time.sleep(settings.metabase_try_sleep_sec)
        setup_token = get_setup_token(base_url)
        if setup_token is not None:
            break

    if setup_token is None:
        logger.error("Metabase on port %s gave no setup token", port)
        return False
    return create_initialuser(base_url, user_data, setup_token)


def get_setup_token(base_url: str) -> str | None:
    try:
        # Metabase is reached inside the Docker network or through the self-signed nginx
        response = requests.get(
            base_url + "/api/session/properties", verify=False, timeout=30  # nosec B501
        )
        return response.json()["setup-token"]
    except Exception as error:
        logger.info("Metabase is not ready: %s", error)
        return None


def create_initialuser(
    base_url: str, user_data: UserDataMetabase, setup_token: str
) -> bool:
    payload = {
        "token": setup_token,
        "prefs": {
            "site_name": "Teaching Course",
            "site_locale": "en",
            "allow_tracking": "false",
        },
        "database": "",
        "invite": "",
        "user": {
            "first_name": user_data.fname,
            "last_name": user_data.lname,
            "email": user_data.email,
            "password": user_data.password,
            "password_confirm": user_data.password,
            "site_name": "Teaching Course",
        },
    }
    try:
        response = requests.post(
            base_url + "/api/setup",
            json=payload,
            timeout=60,
            verify=False,  # nosec B501
        )
    except Exception as error:
        logger.error("Metabase setup request failed: %s", error)
        return False

    if response.status_code == 200:
        logger.info("First Metabase user was created: %s", user_data.email)
        return True
    logger.error("Metabase setup failed with status %s", response.status_code)
    return False
