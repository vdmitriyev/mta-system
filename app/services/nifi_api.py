import logging
from dataclasses import dataclass

from app.services import basic_auth, docker_ctl

logger = logging.getLogger(__name__)


@dataclass
class UserDataNiFi:
    userName: str
    password: str


def create_user_and_docker_nifi(user_data: UserDataNiFi, docker_port: int) -> bool:
    """Creates the NiFi container of a user and the basic auth login for it"""

    if not create_docker_container(docker_port):
        logger.warning("NiFi container was not created. Try to create the login.")
    return basic_auth.set_basic_auth_user(
        user_data.userName, user_data.password, basic_auth.port_auth_file(docker_port)
    )


def create_docker_container(port: int) -> bool:
    if port is None:
        return False
    try:
        container = docker_ctl.get_client().containers.run(
            image="nifi-custom",
            detach=True,
            name=f"nifi-{port}",
            ports={"8080/tcp": ("127.0.0.1", port)},
            environment={
                "NIFI_WEB_HTTP_HOST": "0.0.0.0",  # nosec B104: inside the container
                "NIFI_WEB_HTTP_PORT": "8080",
                "NIFI_WEB_PROXY_CONTEXT_PATH": f"/nifi/{port}/",
            },
            restart_policy={"Name": "unless-stopped", "MaximumRetryCount": 0},
        )
        logger.info("Created NiFi container: %s", container.short_id)
        return True
    except Exception as error:
        logger.error("Cannot create the NiFi container: %s", error)
        return False
