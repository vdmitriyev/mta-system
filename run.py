# -*- encoding: utf-8 -*-

import logging
import logging.config
import os
from os import environ
from sys import exit

from config import config_dict
from webapp import create_app, db

TARGET_SERVER = os.environ.get("TARGET_SERVER") or "development"
SERVER_MODES = ("development", "production")
if TARGET_SERVER.lower() not in SERVER_MODES:
    exit(f"Error: Invalid <TARGET_SERVER> environmental value. Expected values:{SERVER_MODES}")
get_config_mode = TARGET_SERVER

# Load the configuration using the default values
try:
    app_config = config_dict[get_config_mode.lower()]
except KeyError:
    exit(f"Error: Invalid <config_mode>. Expected values {config_dict}")

app = create_app(app_config)


def init_env():
    """Initiate working environment"""
    LOGS_FOLDER = ".logs"
    if not os.path.exists(LOGS_FOLDER):
        os.makedirs(LOGS_FOLDER)


# proper logging in flask via config file
init_env()

if TARGET_SERVER.lower() == "production":
    logging.config.fileConfig("logging-prod.conf")
else:
    logging.config.fileConfig("logging.conf")

logger = logging.getLogger("webapp")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5151, debug=True)
