"""Commands of the app: python -m app.cli <command>"""

import click

from app.cli.config import show_config
from app.cli.database import (
    create_custom_db,
    create_demo_db,
    db_migrate,
    db_upgrade,
    grant_public_schema,
    import_data_exercises,
)
from app.cli.mail import check_mail
from app.cli.nginx import nginx_config
from app.cli.services import service_accounts


@click.group()
def cli():
    """Commands of the mta-system"""


for command in (
    db_upgrade,
    db_migrate,
    import_data_exercises,
    create_demo_db,
    create_custom_db,
    grant_public_schema,
    nginx_config,
    show_config,
    check_mail,
    service_accounts,
):
    cli.add_command(command)
