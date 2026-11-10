import logging
import os
import time
import traceback
from dataclasses import dataclass

import docker

# WORDPRESS_VERSION = '6.2.1'
WORDPRESS_VERSION = "latest"
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK_NAME") or "mtas-network"
WORDPRESS_BASE_URL_DOCKER = (
    os.environ.get("WORDPRESS_BASE_URL_DOCKER") or "http://nginx/wordpress/"
)
SLEEP_TIME_BETWEEN_CONTAINERS_SECONDS = 15
LOGFILE_NAME = "rq-worker.log"
EMAIL_DOMAIN = "e-business01.local"


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


def _silence_logging_noise():
    log_docker = logging.getLogger("docker.utils.config")
    if log_docker is not None:
        log_docker.setLevel(logging.WARNING)
    log_urllib = logging.getLogger("urllib3.connectionpool")
    if log_urllib is not None:
        log_urllib.setLevel(logging.WARNING)


def _configure_logger(logger_path: str):
    """_summary_

    Args:
        logger_path (str): Path to a file with logs
    """

    if logger_path is None:
        logger_path = LOGFILE_NAME

    logging.basicConfig(
        filename=logger_path,
        filemode="a",
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logging.root.name = os.path.basename(__file__)[:-3]


def _build_wordpress_env_config_extra(port: int, user_data):
    wp_base_url = _base_url(user_data.wordpressBaseURL)
    config_output = f"\ndefine('WP_HOME', '{wp_base_url}/{port}/');\n define('WP_SITEURL', WP_HOME);\n $_SERVER['REQUEST_URI'] = str_replace('/wp-admin/','/wordpress/{port}/wp-admin/',$_SERVER['REQUEST_URI']);\n"
    return config_output


def _base_url(wp_base_url):
    if wp_base_url[-1:] == "/":
        wp_base_url = wp_base_url[:-1]
    return wp_base_url


def create_user_and_docker_wordpress(
    user_data: UserDataWordpress, docker_port: int, logger_path: str = None
):
    """Creates docker containers and super use inside for wordpress."""

    _silence_logging_noise()
    _configure_logger(logger_path)

    if not isinstance(user_data, UserDataWordpress):
        logging.error("Must be a UserDatawordpress data type")
        return False

    is_errors = create_docker_container(docker_port, user_data)
    if not is_errors:
        logging.error(f"Status docker creation: {is_errors}")
        logging.warning("Trying anyway to create superuser")

    return True


def _create_htaccess_file_wp(client: object, container_id: str) -> None:
    """Creates .htaccess file inside newly created docker container

    Args:
        container_id (str): _description_
    """
    htaccess_path = "/var/www/html/.htaccess"
    htaccess_content = """
    php_value upload_max_filesize 64M
    php_value post_max_size 64M
    """

    logging.debug(f"Create .htaccess file in the container: {container_id}")

    try:
        container = client.containers.get(container_id)
        container.exec_run(["sh", "-c", f'echo "{htaccess_content}" > {htaccess_path}'])
    except Exception:
        logging.error(traceback.format_exc())


def create_docker_container(port: int, user_data: object):
    """Creates containers for wordpress and runs on the port given"""

    if port is None:
        return False

    try:
        client = docker.from_env()
        res = client.containers.run(
            image=f"wordpress:{WORDPRESS_VERSION}",
            detach=True,
            name=f"wordpress-{port}",
            ports={"80/tcp": ("127.0.0.1", port)},
            restart_policy={"Name": "unless-stopped", "MaximumRetryCount": 0},
            volumes=[f"wordpress-{port}:/var/www/html"],
            network=DOCKER_NETWORK,
            environment={
                "WORDPRESS_DB_HOST": user_data.databaseHost,
                "WORDPRESS_DB_NAME": user_data.databaseName,
                "WORDPRESS_DB_USER": user_data.databaseUser,
                "WORDPRESS_DB_PASSWORD": user_data.databasePassword,
                "WORDPRESS_ADMIN_USER": user_data.wpLogin,
                "WORDPRESS_ADMIN_PASSWORD": user_data.wpPassword,
                "WORDPRESS_ADMIN_EMAIL": f"{user_data.wpLogin}@sample.test",
                "WORDPRESS_CONFIG_EXTRA": _build_wordpress_env_config_extra(
                    port, user_data
                ),
            },
        )

        logging.debug(f"Created wordpress container with id: {res.short_id}")
        logging.debug(f"Sleeping for : {SLEEP_TIME_BETWEEN_CONTAINERS_SECONDS}")

        time.sleep(SLEEP_TIME_BETWEEN_CONTAINERS_SECONDS)
        _create_htaccess_file_wp(client, container_id=res.id)

        # cmd_debug_entrypoint  = "/bin/bash -c \"tail -f /dev/null\""
        cmd_wp_cli_install = f"/bin/bash -c \"sleep 10 && wp core install --url={_base_url(user_data.wordpressBaseURL)} --title='WordPress Site: E-Business' --admin_user={user_data.wpLogin} --admin_password={user_data.wpPassword} --admin_email={user_data.wpEmail} --skip-email\""

        res_cli = client.containers.run(
            image=f"wordpress:cli",
            detach=True,
            name=f"wordpress-cli-{port}",
            # ports = {'80/tcp': ('127.0.0.1', port+10000)},
            restart_policy={"Name": "on-failure", "MaximumRetryCount": 5},
            volumes=[f"wordpress-{port}:/var/www/html"],
            network=DOCKER_NETWORK,
            # entrypoint = cmd_debug_entrypoint,
            command=cmd_wp_cli_install,
            environment={
                "WORDPRESS_DB_HOST": user_data.databaseHost,
                "WORDPRESS_DB_NAME": user_data.databaseName,
                "WORDPRESS_DB_USER": user_data.databaseUser,
                "WORDPRESS_DB_PASSWORD": user_data.databasePassword,
            },  # ,
            # remove=True
        )

        logging.debug(f"Created wordpress CLI container with id: {res_cli.short_id}")

    except ImportError as ex:
        logging.error(f"No module installed: docker. Exception {ex}")
        return False
    except OSError as ex:
        logging.error(f"No access to docker. Exception {ex}")
        return False

    return True


if __name__ == "__main__":
    pass
