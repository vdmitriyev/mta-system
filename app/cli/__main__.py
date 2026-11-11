import sys

from app.cli import cli
from app.config import ConfigError, get_settings
from app.database import init_engine
from app.logging_setup import setup_logging

if __name__ == "__main__":
    try:
        settings = get_settings()
    except ConfigError as error:
        sys.exit(f"Wrong settings: {error}")
    setup_logging(settings.target_server)
    init_engine(settings.database_url)
    cli()
