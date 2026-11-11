import logging
from dataclasses import dataclass

from app.config import get_settings
from app.services import basic_auth, docker_ctl

OPENREFINE_VERSION = "3.9.5"
IMAGE = f"openrefine:{OPENREFINE_VERSION}"
# the image is built from provision/openrefine, it is not in a public registry
IMAGE_HINT = "Build it on the server:"
IMAGE_COMMAND = "docker compose -f compose.services.yml build openrefine-service"

logger = logging.getLogger(__name__)


@dataclass
class UserDataOpenRefine:
    userName: str
    password: str


def create_user_and_docker_or(user_data: UserDataOpenRefine, docker_port: int) -> bool:
    """Creates the OpenRefine container of a user and the basic auth login for it"""

    image = check_image()
    if not image.ok:
        logger.error("OpenRefine is not created: %s", image.text)
        return False
    if not create_docker_container(docker_port):
        logger.warning("OpenRefine container was not created. Try to create the login.")
    return basic_auth.set_basic_auth_user(
        user_data.userName, user_data.password, basic_auth.port_auth_file(docker_port)
    )


def check_image(ask_registry: bool = True) -> docker_ctl.ImageCheck:
    return docker_ctl.check_image(IMAGE, ask_registry, IMAGE_HINT, IMAGE_COMMAND)


def create_docker_container(port: int) -> bool:
    if port is None:
        return False
    try:
        container = docker_ctl.get_client().containers.run(
            image=IMAGE,
            detach=True,
            name=f"openrefine-{port}",
            ports={"80/tcp": ("127.0.0.1", port)},
            network=get_settings().docker_network_name,
            restart_policy={"Name": "unless-stopped", "MaximumRetryCount": 0},
        )
        logger.info("Created OpenRefine container: %s", container.short_id)
        return True
    except Exception as error:
        logger.error("Cannot create the OpenRefine container: %s", error)
        return False
