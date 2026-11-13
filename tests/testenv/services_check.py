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
import urllib.parse
import urllib.request

import pymysql
import requests
import urllib3

from app import surveys
from app.config import get_settings
from app.database import init_engine, session_scope
from app.models import Users
from app.services import basic_auth, docker_ctl, sqlmate_api, surveylite_api
from app.users import access_url, get_user_services

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
    email = user.email
    user_id = user.itid
    access_path = access_url(user).split("/", 3)[3]
print(f"[i] user {email}: accounts {sorted(accounts)}")

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

# ---- sqlmate and SurveyLite: through the nginx of production (variant "names"),
#      else directly (variant "hostports") ----
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
NGINX = os.environ.get("MTAS_NGINX_URL", "").rstrip("/")


def web(session, method: str, public_url: str, direct_base: str, **kwargs):
    """Requests a public address of a service, as a browser of a user does"""

    parts = urllib.parse.urlsplit(public_url)
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    if NGINX:
        return session.request(
            method,
            NGINX + path,
            headers={"Host": parts.hostname},
            verify=False,  # nosec B501: self-signed certificate of the test copy
            allow_redirects=False,
            timeout=30,
            **kwargs,
        )
    return session.request(
        method, direct_base + path, allow_redirects=False, timeout=30, **kwargs
    )


def location_url(response, public_url: str) -> str:
    """Public address of a redirect (absolute or relative)"""

    return urllib.parse.urljoin(public_url, response.headers.get("location", ""))


def follow(session, public_url: str, direct_base: str, max_hops: int = 5):
    """Requests an address and follows the redirects: (last page, its address, paths)"""

    url, hops = public_url, []
    page = web(session, "GET", url, direct_base)
    while page.is_redirect and len(hops) < max_hops:
        url = location_url(page, url)
        hops.append(urllib.parse.urlsplit(url).path)
        page = web(session, "GET", url, direct_base)
    return page, url, hops


# ---- sqlmate ----
sqlmate_direct = settings.sqlmate_api_url.split("/sqlmate/")[0]
entry = accounts.get("sqlmate")
if entry is None or not entry["created"]:
    report("sqlmate", False, f"no account: {entry}")
else:
    try:
        account = sqlmate_api.get_user(entry["sqlmate_login"])
        api_text = f"API knows {account.login}, PIN {'same' if account.pin == entry['sqlmate_pin'] else 'DIFFERENT'}"
        pin_ok = account.pin == entry["sqlmate_pin"]
    except sqlmate_api.SqlmateError as error:
        api_text, pin_ok = f"API: {error}", False
    # the login link logs in and redirects: /sqlmate/sql -> /sqlmate/sql/exercises
    page, url, hops = follow(
        requests.Session(), entry["sqlmate_login_url"], sqlmate_direct
    )
    logged_in = (
        bool(hops)
        and page.status_code == 200
        and not urllib.parse.urlsplit(url).path.endswith("/login")
    )
    report(
        "sqlmate",
        pin_ok and logged_in,
        f"{api_text}; login link -> {' -> '.join(hops)}: {page.status_code}",
    )

# ---- SurveyLite ----
surveylite_direct = settings.surveylite_api_url.split("/api/")[0]
entry = accounts.get("surveylite")
if entry is None or not entry["created"]:
    report("surveylite", False, f"no participant: {entry}")
else:
    try:
        survey_list = surveylite_api.list_surveys()
        survey = survey_list[0]
        # the survey link alone must not be enough: only the logged-in participant
        requests.patch(
            f"{settings.surveylite_api_url.rstrip('/')}/surveys/{survey.id}",
            json={"require_login": True},
            headers={"X-API-Key": settings.surveylite_api_key.get_secret_value()},
            timeout=30,
        ).raise_for_status()
        with session_scope() as db:
            surveys.assign_survey(db, survey, [user_id])
            link = next(
                row
                for row in surveys.refresh_user(db, user_id)
                if row.survey_id == survey.id
            )
            link_url, auth_url, link_status = (
                link.survey_url,
                link.survey_auth_url,
                link.status,
            )
            login_url = surveys.participant_of(db, user_id).surveylite_login_url
        public = settings.surveylite_public_url
        prefix = urllib.parse.urlsplit(public).path.rstrip("/")

        # 1. survey link without login: SurveyLite shows its login form (401)
        plain, plain_url, _ = follow(requests.Session(), link_url, surveylite_direct)
        needs_login = plain.status_code == 401 and 'name="pin"' in plain.text
        # 2. survey link with login (services page): opens the survey
        survey_page, survey_url, _ = follow(
            requests.Session(), auth_url or "", surveylite_direct
        )
        opens_survey = (
            survey_page.status_code == 200
            and urllib.parse.urlsplit(survey_url).path.startswith(f"{prefix}/s/")
            and "auth=" not in survey_url
        )
        # 3. personal login link: opens /me with the survey
        me, me_url, _ = follow(requests.Session(), login_url or "", surveylite_direct)
        link_login = (
            me.status_code == 200
            and urllib.parse.urlsplit(me_url).path == f"{prefix}/me"
            and survey.title in me.text
            and f"{prefix}/static/" in me.text
        )
        # 4. login with the login and the PIN
        browser = requests.Session()
        login = web(
            browser,
            "POST",
            public + "me/login",
            surveylite_direct,
            data={"login": entry["surveylite_login"], "pin": entry["surveylite_pin"]},
        )
        pin_me = web(browser, "GET", public + "me", surveylite_direct)
        pin_login = (
            login.status_code == 303
            and pin_me.status_code == 200
            and survey.title in pin_me.text
        )
        report(
            "surveylite",
            needs_login and opens_survey and link_login and pin_login,
            f'{len(survey_list)} surveys; "{survey.title}" given ({link_status}), '
            f"needs login; survey link alone -> {'login page' if needs_login else f'{plain.status_code} {plain_url}'}, "
            f"with login -> {'survey' if opens_survey else f'{survey_page.status_code} {survey_url}'}; "
            f"login link -> {'/me with the survey' if link_login else f'{me.status_code} {me_url}'}; "
            f"PIN login -> {'/me' if pin_login else f'{login.status_code}/{pin_me.status_code}'}",
        )

        # sqlmate waits for the survey: the services page of the user shows the survey
        app_url = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5151").rstrip("/")
        user_browser = requests.Session()
        user_browser.get(f"{app_url}/{access_path}", timeout=30)
        with session_scope() as db:
            surveys.set_requirement(db, "sqlmate", survey)
        waiting = user_browser.get(f"{app_url}/services", timeout=30).text
        card = waiting[waiting.index('id="service-sqlmate"') :]
        card = card[: card.index("</section>")]
        blocked = "Complete the survey" in card and "Log in to sqlmate" not in card
        with session_scope() as db:
            surveys.set_requirement(db, "sqlmate", None)
        opened = user_browser.get(f"{app_url}/services", timeout=30).text
        free = "Log in to sqlmate" in opened
        report(
            "survey-gate",
            blocked and free,
            f"sqlmate with the survey needed: {'waits' if blocked else 'OPEN'}; "
            f"without: {'open' if free else 'CLOSED'}",
        )
    except Exception as error:
        report("surveylite", False, f"{type(error).__name__}: {error}")

failed = sorted(name for name, ok in results.items() if not ok)
print(
    f"[{'i' if not failed else 'e'}] services that work: "
    f"{sorted(name for name, ok in results.items() if ok)}, failed: {failed}"
)
sys.exit(1 if failed else 0)
