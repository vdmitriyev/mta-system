"""Commands of the flask CLI ($> flask <command>)"""

from .database import (
    create_custom_db,
    create_demo_db,
    grant_public_schema,
    import_data_exercises,
)
from .nginx import nginx_config

COMMANDS = [
    create_demo_db,
    grant_public_schema,
    create_custom_db,
    import_data_exercises,
    nginx_config,
]


def register_commands(app):
    for command in COMMANDS:
        app.cli.add_command(command)
