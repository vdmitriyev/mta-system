"""Command that creates the accounts of the admins (SYSTEM_ADMINS)"""

import click

from app.config import get_settings
from app.database import session_scope
from app.tasks import TaskError
from app.users import (
    access_url,
    assign_available_account,
    find_user_by_email,
    register_new_user,
    send_access_email,
)


@click.command("create-admins")
@click.option("--no-mail", is_flag=True, help="Only print the login data")
def create_admins(no_mail: bool):
    """Creates an account for each e-mail in SYSTEM_ADMINS, prints the login data
    and sends it by e-mail. Existing accounts stay: their login data is printed again.
    """

    admins = get_settings().system_admins
    if not admins:
        raise click.ClickException("SYSTEM_ADMINS is empty: set it in the env file")

    failed = []
    with session_scope() as db:
        for email in admins:
            user = find_user_by_email(db, email)
            if user is None:
                try:
                    user = assign_available_account(db, email) or register_new_user(
                        db, email
                    )
                except TaskError as error:
                    click.echo(f"[!] {email}: not created. {error}")
                    failed.append(email)
                    continue
                state = "created"
            else:
                state = "exists"

            click.echo(f"[i] {email} ({state}, user_id {user.itid})")
            click.echo(f"    PIN:        {user.pin}")
            click.echo(f"    Login link: {access_url(user)}")
            if no_mail:
                continue
            if send_access_email(user):
                click.echo("    E-mail:     sent")
            else:
                click.echo("    E-mail:     not sent (see the log, or: check-mail)")

    if failed:
        raise click.ClickException(f"Not created: {', '.join(failed)}")
