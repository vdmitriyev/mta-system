"""Cron jobs of the app. ofelia runs them as commands (provision/ofelia/config.ini).

Nightly stop of the users' containers (Metabase, OpenRefine): frees RAM and CPU.
"python -m app.cli stop-containers" at 03:15. The users start their containers again
with "Start service" on the page Services.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.admin_log import log_action
from app.models import CONTAINER_SERVICES, SERVICE_MODELS
from app.service_settings import SERVICE_INFO
from app.services import docker_ctl
from app.users import container_name

# seconds until Docker kills a container: Metabase needs time to close its database
STOP_TIMEOUT = 60

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunningContainer:
    user_id: int
    service: str
    name: str


def running_containers(db: Session, services: list) -> list[RunningContainer]:
    """The running containers of the users for these services"""

    found = []
    for service in services:
        if service not in CONTAINER_SERVICES:
            logger.warning("%s has no containers of the users: skipped", service)
            continue
        model = SERVICE_MODELS[service]
        for entry in db.query(model).filter(model.deleted.is_(False)):
            name = container_name(service, entry)
            if name:
                found.append(RunningContainer(entry.user_id, service, name))
    statuses = docker_ctl.container_statuses([c.name for c in found])
    return [c for c in found if statuses.get(c.name) == "running"]


def stop_user_containers(db: Session, services: list) -> list[RunningContainer]:
    """Stops the running containers and notes each one in the admin log"""

    stopped = []
    for container in running_containers(db, services):
        if not docker_ctl.run_action(container.name, "stop", timeout=STOP_TIMEOUT):
            continue
        title = SERVICE_INFO[container.service].name
        log_action(
            db,
            None,
            "service_stop_night",
            container.user_id,
            details=f"{title}: {container.name}",
        )
        stopped.append(container)
    logger.info("Nightly stop: %s containers stopped", len(stopped))
    return stopped
