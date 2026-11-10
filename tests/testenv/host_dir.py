"""Prints the project folder as the Docker daemon sees it.

Bind mounts need paths of the machine that runs the Docker daemon. Inside a
container that uses the daemon of its host (e.g. Docker Desktop), these differ
from the paths inside the container.
"""

import http.client
import json
import os
import socket

DOCKER_SOCKET = "/var/run/docker.sock"


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(5)
        self.sock.connect(DOCKER_SOCKET)


def to_daemon_path(path: str) -> str:
    """Docker Desktop on Windows: C:\\x\\y -> /run/desktop/mnt/host/c/x/y"""

    if len(path) > 2 and path[1] == ":":
        return "/run/desktop/mnt/host/" + path[0].lower() + path[2:].replace("\\", "/")
    return path


def host_dir(project_dir: str) -> str:
    if not (os.path.exists("/.dockerenv") and os.path.exists(DOCKER_SOCKET)):
        return project_dir

    try:
        conn = UnixHTTPConnection("localhost")
        conn.request("GET", f"/containers/{socket.gethostname()}/json")
        response = conn.getresponse()
        if response.status != 200:
            return project_dir
        mounts = json.load(response).get("Mounts", [])
    except OSError:
        return project_dir

    for mount in mounts:
        target = mount["Destination"]
        if mount["Type"] == "bind" and (
            project_dir == target or project_dir.startswith(target + "/")
        ):
            return to_daemon_path(mount["Source"] + project_dir[len(target) :])

    return project_dir


if __name__ == "__main__":
    print(host_dir(os.getcwd()))
