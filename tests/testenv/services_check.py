"""Checks the services of the newest user of the test copy (after e2e.py registered one).

Runs inside the app container: task testenv:check
Reports every service, then fails if one of them does not work.
"""

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request

import pymysql

from app.config import get_settings
from app.database import init_engine, session_scope
from app.models import Users
from app.services import basic_auth, docker_ctl
from app.users import get_user_services

settings = get_settings()
results = {}


def report(service: str, ok: bool, text: str) -> None:
    results[service] = ok
    print(f"[{'i' if ok else 'e'}] {service}: {text}")


def fetch(url: str, data: dict | None = None, headers: dict | None = None):
    """Returns (status, body). Errors of the connection give status 0."""

    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers or {})
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")
    except OSError as error:
        return 0, str(error)


def url_of(error) -> str:
    return getattr(error, "url", "") or ""


def container_url(service: str, port: int) -> str:
    """Address of a container of a user, as the app reaches it"""

    if settings.container_publish_ports:
        return f"http://127.0.0.1:{port}"
    return f"http://{docker_ctl.container_name(service, port)}"


def wait_for(url: str, ok, seconds: int) -> tuple:
    """Requests the URL until ok(status, body) is true or the time is over"""

    status, body = 0, ""
    for _ in range(seconds // 5):
        status, body = fetch(url)
        if ok(status, body):
            break
        time.sleep(5)
    return status, body


def container_state(service: str, port: int) -> str:
    name = docker_ctl.container_name(service, port)
    return docker_ctl.container_statuses([name]).get(name, docker_ctl.UNKNOWN)


init_engine(settings.database_url)
with session_scope() as db:
    user = db.query(Users).order_by(Users.itid.desc()).first()
    services = get_user_services(db, user.itid)
    # read all values before the session closes
    accounts = {
        name: {
            column.name: getattr(entry, column.name)
            for column in entry.__table__.columns
        }
        for name, entry in services.items()
    }
print(f"[i] user {user.email}: accounts {sorted(accounts)}")

# ---- pgAdmin 4 ----
entry = accounts.get("pgadmin4")
if entry is None:
    report("pgadmin4", False, "no account")
else:
    login = basic_auth.login_state(
        entry["pgadmin4_user"],
        entry["pgadmin4_password"],
        basic_auth.common_auth_file(),
    )
    base = os.environ.get("MTAS_PGADMIN4_URL", "http://pgadmin4").rstrip("/")
    status, body = wait_for(
        f"{base}/misc/ping", lambda s, b: s == 200 and "PING" in b, 120
    )
    # nginx passes the login on like this. pgAdmin logs the user in on /login and
    # keeps the session in a cookie: follow the redirects with cookies, as a browser does.
    pgadmin = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    request = urllib.request.Request(
        f"{base}/browser/", headers={"X-Forwarded-User": entry["pgadmin4_user"]}
    )
    try:
        with pgadmin.open(request, timeout=30) as response:
            browser, page = response.status, response.read().decode(errors="replace")
            final_url = response.geturl()
    except urllib.error.HTTPError as error:
        browser, page, final_url = error.code, "", url_of(error)
    except OSError as error:
        browser, page, final_url = 0, str(error), ""
    browser = browser if "/login" not in final_url else 401
    ok = login == basic_auth.LOGIN_OK and status == 200 and browser == 200
    report(
        "pgadmin4",
        ok,
        f"login file {login}, ping {status}, browser as {entry['pgadmin4_user']}: {browser}",
    )

# ---- Metabase ----
entry = accounts.get("metabase")
if entry is None:
    report("metabase", False, "no account")
else:
    port = entry["metabase_docker_port"]
    base = container_url("metabase", port)
    status, body = wait_for(
        f"{base}/api/health", lambda s, b: s == 200 and '"ok"' in b, 300
    )
    session, answer = fetch(
        f"{base}/api/session",
        {"username": entry["metabase_login"], "password": entry["metabase_password"]},
    )
    ok = entry["created"] and status == 200 and session == 200
    report(
        "metabase",
        ok,
        f"container {container_state('metabase', port)}, created {entry['created']}, "
        f"health {status}, login of the user {session} {answer[:120] if session != 200 else ''}",
    )

# ---- OpenRefine ----
entry = accounts.get("openrefine")
if entry is None:
    report("openrefine", False, "no account")
else:
    port = entry["openrefine_docker_port"]
    base = container_url("openrefine", port)
    status, body = wait_for(
        f"{base}/command/core/get-version", lambda s, b: s == 200, 180
    )
    login = basic_auth.login_state(
        entry["openrefine_user"],
        entry["openrefine_password"],
        basic_auth.port_auth_file(port),
    )
    ok = status == 200 and login == basic_auth.LOGIN_OK
    report(
        "openrefine",
        ok,
        f"container {container_state('openrefine', port)}, version {body[:80]!r}, "
        f"status {status}, login file {login}",
    )

# ---- MariaDB ----
mariadb = accounts.get("mariadb")
if mariadb is None:
    report("mariadb", False, "no account")
else:
    try:
        connection = pymysql.connect(
            host=settings.mariadb_db_host,
            port=settings.mariadb_db_host_port,
            user=mariadb["mariadb_user"],
            password=mariadb["mariadb_password"],
            database=mariadb["mariadb_db"],
            connect_timeout=10,
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
        connection.close()
        report("mariadb", True, f"login of {mariadb['mariadb_user']}, server {version}")
    except Exception as error:
        report("mariadb", False, f"login failed: {error}")

# ---- WordPress ----
entry = accounts.get("wordpress")
if entry is None:
    report("wordpress", False, "no account")
else:
    port = entry["wordpress_docker_port"]
    installed, site_url = False, None
    # WP-CLI installs WordPress in its own container: wait for the tables
    for _ in range(36):
        try:
            connection = pymysql.connect(
                host=settings.mariadb_db_host,
                port=settings.mariadb_db_host_port,
                user=mariadb["mariadb_user"],
                password=mariadb["mariadb_password"],
                database=mariadb["mariadb_db"],
                connect_timeout=10,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT option_value FROM wp_options WHERE option_name = 'siteurl'"
                )
                row = cursor.fetchone()
            connection.close()
            if row:
                installed, site_url = True, row[0]
                break
        except Exception:
            pass
        time.sleep(5)
    status, _body = fetch(f"{container_url('wordpress', port)}/wp-login.php")
    ok = installed and status in (200, 301, 302)
    report(
        "wordpress",
        ok,
        f"container {container_state('wordpress', port)}, installed {installed} "
        f"(siteurl {site_url}), wp-login.php {status}",
    )

failed = sorted(name for name, ok in results.items() if not ok)
print(
    f"[{'i' if not failed else 'e'}] services that work: "
    f"{sorted(name for name, ok in results.items() if ok)}, failed: {failed}"
)
sys.exit(1 if failed else 0)
