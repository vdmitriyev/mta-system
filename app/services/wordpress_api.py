import logging
import time
from dataclasses import dataclass

from app.config import get_settings
from app.services import docker_ctl

WORDPRESS_VERSION = "latest"
SLEEP_TIME_BETWEEN_CONTAINERS_SECONDS = 15

HTACCESS_PATH = "/var/www/html/.htaccess"
HTACCESS_CONTENT = """
php_value upload_max_filesize 64M
php_value post_max_size 64M
"""

logger = logging.getLogger(__name__)


@dataclass
class UserDataWordpress:
    wpLogin: str
    wpPassword: str
    wpEmail: str
    databaseHost: str
    databaseName: str
    databaseUser: str
    databasePassword: str
    wordpressBaseURL: str


def _base_url(wp_base_url: str) -> str:
    return wp_base_url.rstrip("/")


def _build_wordpress_env_config_extra(port: int, user_data: UserDataWordpress) -> str:
    """PHP lines for wp-config.php: WordPress runs under /wordpress/<port>/"""

    wp_base_url = _base_url(user_data.wordpressBaseURL)
    return (
        f"\ndefine('WP_HOME', '{wp_base_url}/{port}/');\n"
        " define('WP_SITEURL', WP_HOME);\n"
        " $_SERVER['REQUEST_URI'] = str_replace('/wp-admin/',"
        f"'/wordpress/{port}/wp-admin/',$_SERVER['REQUEST_URI']);\n"
    )


def create_user_and_docker_wordpress(
    user_data: UserDataWordpress, docker_port: int
) -> bool:
    """Creates the WordPress container of a user and installs WordPress in it.

    Takes about half a minute: call it from a background task.
    """

    if docker_port is None:
        return False

    database = {
        "WORDPRESS_DB_HOST": user_data.databaseHost,
        "WORDPRESS_DB_NAME": user_data.databaseName,
        "WORDPRESS_DB_USER": user_data.databaseUser,
        "WORDPRESS_DB_PASSWORD": user_data.databasePassword,
    }
    network = get_settings().docker_network_name
    volumes = [f"wordpress-{docker_port}:/var/www/html"]

    try:
        client = docker_ctl.get_client()
        container = client.containers.run(
            image=f"wordpress:{WORDPRESS_VERSION}",
            detach=True,
            name=f"wordpress-{docker_port}",
            ports={"80/tcp": ("127.0.0.1", docker_port)},
            restart_policy={"Name": "unless-stopped", "MaximumRetryCount": 0},
            volumes=volumes,
            network=network,
            environment={
                **database,
                "WORDPRESS_CONFIG_EXTRA": _build_wordpress_env_config_extra(
                    docker_port, user_data
                ),
            },
        )
        logger.info("Created WordPress container: %s", container.short_id)

        # WordPress copies its files into the volume on the first start
        time.sleep(SLEEP_TIME_BETWEEN_CONTAINERS_SECONDS)
        container.exec_run(["sh", "-c", f'echo "{HTACCESS_CONTENT}" > {HTACCESS_PATH}'])

        install = (
            "wp core install"
            f" --url={_base_url(user_data.wordpressBaseURL)}"
            " --title='WordPress Site: E-Business'"
            f" --admin_user={user_data.wpLogin}"
            f" --admin_password={user_data.wpPassword}"
            f" --admin_email={user_data.wpEmail}"
            " --skip-email"
        )
        cli_container = client.containers.run(
            image="wordpress:cli",
            detach=True,
            name=f"wordpress-cli-{docker_port}",
            restart_policy={"Name": "on-failure", "MaximumRetryCount": 5},
            volumes=volumes,
            network=network,
            command=f'/bin/bash -c "sleep 10 && {install}"',
            environment=database,
        )
        logger.info("Created WordPress CLI container: %s", cli_container.short_id)
        return True
    except Exception as error:
        logger.error("Cannot create the WordPress containers: %s", error)
        return False
