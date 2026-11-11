"""Command that shows or changes the services in which new users get an account"""

import click

from app.database import session_scope
from app.service_settings import (
    SERVICE_KEYS,
    ServiceSettingError,
    add_default_service_settings,
    service_setting_rows,
    set_creates_accounts,
)


@click.command("service-accounts")
@click.option("--on", "switch_on", multiple=True, type=click.Choice(SERVICE_KEYS))
@click.option("--off", "switch_off", multiple=True, type=click.Choice(SERVICE_KEYS))
def service_accounts(switch_on, switch_off):
    """Shows or changes in which services new users get an account"""

    with session_scope() as db:
        add_default_service_settings(db)
        try:
            # off first: "--off wordpress --off mariadb" and "--on mariadb --on wordpress" work
            for service in sorted(switch_off, key=lambda s: s == "mariadb"):
                set_creates_accounts(db, service, False)
            for service in sorted(switch_on, key=lambda s: s == "wordpress"):
                set_creates_accounts(db, service, True)
        except ServiceSettingError as error:
            raise click.ClickException(str(error))
        for row in service_setting_rows(db):
            click.echo(f"{row.service:<12} {'on' if row.create_accounts else 'off'}")
