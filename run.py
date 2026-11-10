# -*- encoding: utf-8 -*-

import logging

from helpers import (
    change_logging_level_requests,
    get_app_config,
    get_target_server,
    init_env,
    load_envs,
)

load_envs()
init_env()
target_server = get_target_server()
app_config = get_app_config(target_server)

change_logging_level_requests(level=logging.getLevelName("WARNING"))

from app.app import create_app

app = create_app(app_config)

logger = logging.getLogger("app")
app.logger.handlers = logger.handlers

log_docker = logging.getLogger("docker.utils.config")
log_docker.setLevel(logging.WARNING)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5151, debug=True)
