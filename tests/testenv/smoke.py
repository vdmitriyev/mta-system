"""Checks that the main pages of the test copy answer.

Runs inside the app container: task testenv:check
"""

import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5151").rstrip("/")
PAGES = ["/", "/about", "/login", "/register", "/api/health", "/static/css/app.css"]


def check(path: str) -> bool:
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=10) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except OSError as error:
        print(f"[e] {path}: {error}")
        return False

    print(f"[{'i' if status == 200 else 'e'}] {path}: {status}")
    return status == 200


if __name__ == "__main__":
    results = [check(path) for path in PAGES]
    sys.exit(0 if all(results) else 1)
