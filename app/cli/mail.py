"""Command that checks the connection to the SMTP server"""

import click

from app.config import get_settings
from app.emails import connect, describe_error, send_email


@click.command("check-mail")
@click.option("--to", "to_email", default=None, help="Also sends a test e-mail here")
def check_mail(to_email):
    """Connects and logs in to the SMTP server of the settings (MAIL_*)"""

    settings = get_settings()
    click.echo(f"SMTP server: {settings.mail_server}:{settings.mail_port}")
    try:
        with connect(settings):
            pass
    except OSError as error:
        raise click.ClickException(describe_error(error, settings))
    click.echo("Connection and login work.")

    if to_email:
        if not send_email(to_email, "Test", "Test e-mail of mta-system.", settings):
            raise click.ClickException("The test e-mail was not sent. See the log.")
        click.echo(f"Test e-mail was sent to {to_email}.")
