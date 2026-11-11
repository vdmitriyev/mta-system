"""Access to the Docker daemon. All functions work without Docker (they return empty results)."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"


@dataclass
class ImageCheck:
    """Result of check_image: "<state>: <image>", then the hint and the command to fix it"""

    ok: bool
    state: str
    image: str
    hint: str = ""
    command: str = ""

    @property
    def text(self) -> str:
        """All in one line, for logs and task messages"""

        text = f"{self.state}: {self.image}."
        if self.hint:
            text += f" {self.hint}"
        if self.command:
            text += f" {self.command}"
        return text


def get_client():
    import docker

    return docker.from_env()


def _client_or_none():
    try:
        return get_client()
    except Exception as error:
        logger.error("No access to Docker: %s", error)
        return None


def list_containers(only_running: bool = False) -> list:
    client = _client_or_none()
    if client is None:
        return []
    try:
        return client.containers.list(all=not only_running)
    except Exception as error:
        logger.error("Cannot list the Docker containers: %s", error)
        return []


def container_statuses(names: list) -> dict:
    """Gets the status of the given containers: name -> status ("running", "exited", ...)"""

    wanted = {name for name in names if name}
    statuses = {name: UNKNOWN for name in wanted}
    if not wanted:
        return statuses
    for container in list_containers():
        if container.name in wanted:
            statuses[container.name] = container.status
    return statuses


def run_action(container_name: str, action: str) -> bool:
    """Starts or stops a container. Returns True if the container was found."""

    if action not in ("start", "stop"):
        raise ValueError(f"Action is not supported: {action}")

    client = _client_or_none()
    if client is None or not container_name:
        return False
    try:
        container = client.containers.get(container_name)
        getattr(container, action)()
        logger.info("Container %s: %s", container_name, action)
        return True
    except Exception as error:
        logger.error("Container %s: %s failed: %s", container_name, action, error)
        return False


def retire_container(name: str, new_name: str) -> bool:
    """Stops a container and renames it, so a new one can get its name"""

    for container in list_containers():
        if container.name == name:
            try:
                container.rename(new_name)
                container.stop()
                logger.info("Container %s was renamed to %s", name, new_name)
                return True
            except Exception as error:
                logger.error("Cannot retire the container %s: %s", name, error)
                return False
    return False


def containers_info(log_lines: int = 20) -> list:
    """Gets id, name, image, status and the last log lines of all containers"""

    containers = []
    for container in list_containers():
        try:
            logs = container.logs(tail=log_lines).decode(errors="replace")
        except Exception as error:
            logs = f"Cannot read the logs: {error}"
        try:
            image = ", ".join(container.image.tags) or container.image.short_id
        except Exception:
            image = UNKNOWN
        containers.append(
            {
                "id": container.short_id,
                "name": container.name,
                "image": image,
                "status": container.status,
                "logs": logs,
            }
        )
    return containers


def containers_summary() -> dict:
    containers = list_containers()
    running = sum(1 for container in containers if container.status == "running")
    return {
        "total": len(containers),
        "running": running,
        "exited": len(containers) - running,
    }


def _is_not_found(error: Exception) -> bool:
    from docker.errors import NotFound

    return isinstance(error, NotFound)


def check_image(
    image: str, ask_registry: bool = True, hint: str = "", command: str = ""
) -> ImageCheck:
    """Checks that the image (name:version) is on this server or in its registry.

    Without ask_registry only this server is checked (fast, for pages).
    hint and command tell how to get the image, if it is missing.
    """

    missing = {"hint": hint, "command": command}
    client = _client_or_none()
    if client is None:
        return ImageCheck(
            False, "No access to Docker (is the Docker socket mounted?)", image
        )
    try:
        client.images.get(image)
        return ImageCheck(True, "Image is on this server", image)
    except Exception as error:
        if not _is_not_found(error):
            logger.error("Cannot check the image %s: %s", image, error)
            return ImageCheck(False, f"Cannot check the image ({error})", image)

    if not ask_registry:
        return ImageCheck(False, "Image is not on this server", image, **missing)
    try:
        client.images.get_registry_data(image)
        return ImageCheck(
            True,
            "Image is in the registry, Docker downloads it on the first start",
            image,
        )
    except Exception as error:
        logger.error("Image %s is not in the registry: %s", image, error)
        return ImageCheck(
            False,
            "Image is not on this server and not in the registry",
            image,
            **missing,
        )
