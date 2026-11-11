"""Command that shows the settings of the app"""

import click

from app.config import env_file, get_settings


@click.command("show-config")
def show_config():
    """Shows the env file and the settings (without passwords and keys)"""

    path = env_file()
    state = "found" if path.is_file() else "not found, only environment variables"
    click.echo(f"# env file: {path} ({state})")
    for key, value in get_settings().public_items().items():
        if isinstance(value, list):
            value = ";".join(value)
        click.echo(f"{key}={'' if value is None else value}")
