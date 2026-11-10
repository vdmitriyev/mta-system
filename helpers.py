import logging
import logging.config
import os
from datetime import datetime

from dotenv import load_dotenv


def load_envs():
    """Loads environmental variables from the file"""

    env_file = os.environ.get("ENV_FILE_NAME") or None
    basedir = os.path.abspath(os.path.dirname(__file__))

    def load_from_default_env():
        DEFAULT_ENV_FILE_NAME = os.path.join("envs", "webapp-dev-local.env")
        print(
            f"{datetime.now()} trying to load default env file: {DEFAULT_ENV_FILE_NAME}"
        )
        load_dotenv(os.path.join(basedir, DEFAULT_ENV_FILE_NAME), override=True)

    if env_file is not None:
        if os.path.exists(env_file):
            print(f"{datetime.now()} loading environmental file: {env_file}")
            load_dotenv(env_file, override=True)
        else:
            print(f"{datetime.now()} provided env file does not exist: {env_file}")
            load_from_default_env()
    else:
        print(f"{datetime.now()} not env file has been provided")
        load_from_default_env()


def print_all_envs_values():
    import os

    for item, value in os.environ.items():
        print("{}: {}".format(item, value))


def get_target_server():
    TARGET_SERVER = os.environ.get("TARGET_SERVER") or "development"
    SERVER_MODES = ("development", "production")
    if TARGET_SERVER.lower() not in SERVER_MODES:
        print(
            f"Error: Invalid <TARGET_SERVER> environmental value. Expected values:{SERVER_MODES}"
        )
        TARGET_SERVER = "development"
    return TARGET_SERVER


def get_app_config(target_server):
    app_config = None

    if target_server.lower() == "development":
        # app_config = config_dict[target_server.lower()]
        from config import DevelopmentConfig

        app_config = DevelopmentConfig
        logging.config.fileConfig("configs-logging/logging.conf")

    if target_server.lower() == "production":
        # app_config = config_dict[target_server.lower()]
        from config import ProductionConfig

        app_config = ProductionConfig
        logging.config.fileConfig("configs-logging/logging-prod.conf")

    return app_config


def init_env():
    """Initiate working environment"""
    LOGS_FOLDER = ".logs"
    if not os.path.exists(LOGS_FOLDER):
        os.makedirs(LOGS_FOLDER)


def change_logging_level_requests(level: int):
    """Changes logging level for all requests done within the module"""

    import logging
    from datetime import datetime

    import requests

    print(
        f"{datetime.now()} set log level for requests to: {logging.getLevelName(level)}"
    )
    logging.getLogger("urllib3.connectionpool").setLevel(level)
