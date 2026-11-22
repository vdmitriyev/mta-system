"""Command "stop-containers": the nightly stop of the users' containers (ofelia)"""

import click

from app.config import get_settings
from app.cronjobs import running_containers, stop_user_containers
from app.database import session_scope
from app.models import CONTAINER_SERVICES


@click.command("stop-containers")
@click.option(
    "--service",
    "services",
    multiple=True,
    type=click.Choice(CONTAINER_SERVICES),
    help="Only these services (default: NIGHT_STOP_SERVICES)",
)
@click.option("--dry-run", is_flag=True, help="Only list the running containers")
def stop_containers(services, dry_run):
    """Stops the running containers of the users (Metabase, OpenRefine) to free RAM and CPU"""

    services = list(services) or get_settings().night_stop_services
    with session_scope() as db:
        if dry_run:
            containers = running_containers(db, services)
            for container in containers:
                click.echo(
                    f"[i] would stop {container.name} (user {container.user_id})"
                )
            click.echo(f"[i] running containers: {len(containers)}")
            return
        stopped = stop_user_containers(db, services)
    for container in stopped:
        click.echo(f"[i] stopped {container.name} (user {container.user_id})")
    click.echo(f"[i] stopped containers: {len(stopped)} ({', '.join(services) or '-'})")
