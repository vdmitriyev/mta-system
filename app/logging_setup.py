import logging
import logging.config
import os

from app.config import BASE_DIR

LOGGING_CONFIGS = {
    "development": "logging.conf",
    "production": "logging-prod.conf",
}

# These libraries log every request and every config lookup at DEBUG level
NOISY_LOGGERS = (
    "urllib3.connectionpool",
    "docker.utils.config",
    "multipart",
    "python_multipart",
    "PIL",
)


def setup_logging(target_server: str) -> None:
    """Sets up the logging from configs-logging/ (the log files are in .logs/)"""

    os.makedirs(".logs", exist_ok=True)
    config_file = BASE_DIR / "configs-logging" / LOGGING_CONFIGS[target_server]
    logging.config.fileConfig(config_file, disable_existing_loggers=False)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
