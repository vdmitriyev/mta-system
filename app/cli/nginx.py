"""Generates the parts of the nginx config for the service containers of the students.

Every user of a service gets an own location with basic auth:
the port of the user's container is part of the URL and of the .htpasswd file name.
nginx-docker.conf includes the generated files (see provision/nginx).

$> python -m app.cli nginx-config                       # all services, into provision/nginx
$> python -m app.cli nginx-config -s openrefine -n 50   # only OpenRefine, for 50 users
"""

import os

import click

from app.config import (
    MAX_USERS_NGINX_GENERATE,
    NIFI_PORT_OFFSET,
    OPENREFINE_PORT_OFFSET,
)

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_TARGET_DIR = os.path.join(PROJECT_DIR, "provision", "nginx")

# Folder with the .htpasswd files, as the nginx container sees it (compose: ./.htpasswd_nginx)
DEFAULT_HTPASSWD_DIR = "/.htpasswd_nginx/"


################################################################################
# OpenRefine
#
# URL:        https://<server>/openrefine/<port>/
# Forwards to the container "openrefine-<port>" (Docker DNS, resolver 127.0.0.11).
#             The container name comes from app/services/openrefine_api.py.
# Login:      <htpasswd_dir>/<port>.htpasswd
# Ports:      OPENREFINE_PORT_OFFSET + 1, + 2, ... (app/config.py)
#
# Placeholders in the template: {port}, {htpasswd_dir}
# Double braces {{ }} are single braces in the nginx config.
################################################################################

OPENREFINE_CONFIG_FILE = "nginx_part_openrefine.config"

OPENREFINE_HEADER = """

    ################################################################
    # START: Configuration for separated basic auth of OpenRefine
    ################################################################

"""

# One location per user. "rewrite" removes /openrefine/<port> from the path,
# because OpenRefine itself runs on "/".
OPENREFINE_LOCATION = """
    location /openrefine/{port}/ {{
        resolver 127.0.0.11;
        auth_basic "Restricted Content";
        auth_basic_user_file {htpasswd_dir}{port}.htpasswd;
        rewrite ^/openrefine/{port}/(.*)$ /$1 break;
        proxy_pass http://openrefine-{port}/$1$is_args$args;
    }}
"""

OPENREFINE_FOOTER = """

    ################################################################
    # END: Configuration for separated basic auth of OpenRefine
    ################################################################
"""


################################################################################
# NiFi
#
# URL:        https://<server>/nifi/<port>/
# Forwards to 127.0.0.1:<port>: this works only with nginx on the host itself,
#             not in the nginx container (there, 127.0.0.1 is the container).
#             The NiFi containers are named "nifi-<port>" (app/services/nifi_api.py).
# Login:      <htpasswd_dir>/<port>.htpasswd
# Ports:      NIFI_PORT_OFFSET + 1, + 2, ... (app/config.py)
#
# Placeholders in the template: {port}, {htpasswd_dir}
# Double braces {{ }} are single braces in the nginx config.
################################################################################

NIFI_CONFIG_FILE = "nginx_part_nifi.config"

NIFI_HEADER = """

    ################################################################
    # START: Configuration for separated basic auth of NiFi
    ################################################################

"""

# One location per user. NiFi needs the X-Proxy* headers to build its links
# under /nifi/<port>/. "Authorization" is emptied: NiFi must not get the basic auth login.
NIFI_LOCATION = """
    location /nifi/{port}/ {{

        auth_basic "Restricted Content";
        auth_basic_user_file {htpasswd_dir}{port}.htpasswd;
        proxy_pass http://127.0.0.1:{port}/;
        proxy_redirect off;

        proxy_set_header   Host                 $host;
        proxy_set_header   X-Real-IP            $remote_addr;
        proxy_set_header   X-Forwarded-For      $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto    $scheme;
        proxy_set_header   X-Forwarded-User     $remote_user;
        proxy_set_header   Authorization        "";
        proxy_set_header   X-ProxyScheme        $scheme;
        proxy_set_header   X-ProxyHost          $server_name;
        proxy_set_header   X-ProxyPort          $server_port;
        proxy_set_header   X-ProxyContextPath   /nifi/{port}/;
    }}
"""

NIFI_FOOTER = """

    ################################################################
    # END: Configuration for separated basic auth of NiFi
    ################################################################
"""


################################################################################
# Shared code: writes header, one location per user, footer
################################################################################


def write_config(
    path: str,
    header: str,
    location: str,
    footer: str,
    port_offset: int,
    max_users: int,
    htpasswd_dir: str,
):
    """Writes a config part with one location per user (ports port_offset + 1 ... + max_users)"""

    htpasswd_dir = htpasswd_dir.rstrip("/") + "/"

    with open(path, "w") as config_file:
        config_file.write(header)
        for user_number in range(1, max_users + 1):
            config_file.write(
                location.format(
                    port=port_offset + user_number, htpasswd_dir=htpasswd_dir
                )
            )
        config_file.write(footer)


def create_openrefine_config(target_dir: str, max_users: int, htpasswd_dir: str):
    path = os.path.join(target_dir, OPENREFINE_CONFIG_FILE)
    write_config(
        path,
        header=OPENREFINE_HEADER,
        location=OPENREFINE_LOCATION,
        footer=OPENREFINE_FOOTER,
        port_offset=OPENREFINE_PORT_OFFSET,
        max_users=max_users,
        htpasswd_dir=htpasswd_dir,
    )
    click.echo(f"[i] OpenRefine: {max_users} locations in {path}")


def create_nifi_config(target_dir: str, max_users: int, htpasswd_dir: str):
    path = os.path.join(target_dir, NIFI_CONFIG_FILE)
    write_config(
        path,
        header=NIFI_HEADER,
        location=NIFI_LOCATION,
        footer=NIFI_FOOTER,
        port_offset=NIFI_PORT_OFFSET,
        max_users=max_users,
        htpasswd_dir=htpasswd_dir,
    )
    click.echo(f"[i] NiFi: {max_users} locations in {path}")


SERVICES = {
    "openrefine": create_openrefine_config,
    "nifi": create_nifi_config,
}


################################################################################
# CLI: $> python -m app.cli nginx-config
################################################################################


@click.command("nginx-config")
@click.option(
    "--service",
    "-s",
    type=click.Choice(["all", *SERVICES]),
    default="all",
    show_default=True,
    help="Service to create the config part for",
)
@click.option(
    "--target-dir",
    "-t",
    type=click.Path(exists=True, file_okay=False, writable=True),
    default=DEFAULT_TARGET_DIR,
    show_default=True,
    help="Folder to save the config files in",
)
@click.option(
    "--htpasswd-dir",
    "-d",
    default=DEFAULT_HTPASSWD_DIR,
    show_default=True,
    help="Folder with the .htpasswd files, as nginx sees it",
)
@click.option(
    "--max-users",
    "-n",
    type=click.IntRange(min=1),
    default=MAX_USERS_NGINX_GENERATE,
    show_default=True,
    help="Number of users (one location per user)",
)
def nginx_config(service: str, target_dir: str, htpasswd_dir: str, max_users: int):
    """Creates the nginx config parts for OpenRefine and NiFi (basic auth per user)"""

    names = list(SERVICES) if service == "all" else [service]
    for name in names:
        SERVICES[name](target_dir, max_users, htpasswd_dir)
