"""Checks the main flow of the test copy: register, log in, see the services, import a dataset.

Runs inside the app container: task testenv:check
"""

import base64
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid

import psycopg2

from app.config import get_settings
from app.database import init_engine, session_scope
from app.security import make_hash
from app.users import find_user_by_email, get_user_services

BASE_URL = "http://127.0.0.1:5151"
EMAIL = f"e2e.check{uuid.uuid4().hex[:6]}@example.org"

settings = get_settings()
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path: str) -> str:
    with opener.open(BASE_URL + path, timeout=30) as response:
        return response.read().decode()


def post(path: str, **data) -> tuple:
    """Sends a form. Returns the page after the redirect and its address."""

    body = urllib.parse.urlencode(data).encode()
    with opener.open(BASE_URL + path, data=body, timeout=60) as response:
        return response.read().decode(), response.geturl()


def csrf(page: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def captcha_text() -> str:
    """Finds the digits of the captcha: the session cookie holds their hash"""

    cookie = next(c.value for c in jar if c.name == "mtas_session")
    payload = cookie.split(".")[0]
    session = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4)))
    for number in range(10000):
        text = str(number).zfill(4)
        if (
            make_hash(text, settings.hash_key_hidden.get_secret_value())
            == session["captcha"]
        ):
            return text
    raise SystemExit("[e] captcha was not found")


def wait_for_task(task_id: str, seconds: int = 180) -> dict:
    for _ in range(seconds):
        task = json.loads(get(f"/api/tasks/{task_id}"))
        if task["finished"]:
            return task
        time.sleep(1)
    raise SystemExit(f"[e] task did not finish: {task_id}")


def step(text: str, ok: bool) -> None:
    print(f"[{'i' if ok else 'e'}] {text}")
    if not ok:
        sys.exit(1)


# register
page = get("/register")
_page, status_url = post(
    "/register",
    csrf_token=csrf(page),
    email=EMAIL,
    code=settings.course_security_code,
    captcha=captcha_text(),
)
task = wait_for_task(status_url.rsplit("/", 1)[-1])
# the test copy has no mail server: the account is set up, the e-mail is not sent
step(
    f"registration of {EMAIL}: {task['message']}",
    task["status"] == "done" or "could not send the e-mail" in task["message"],
)

init_engine(settings.database_url)
with session_scope() as db:
    user = find_user_by_email(db, EMAIL)
    services = get_user_services(db, user.itid)
step(f"accounts of the user: {sorted(services)}", "postgresql" in services)
step("PostgreSQL database was created", services["postgresql"].created)

# log in with e-mail and PIN
jar.clear()
page, _url = post("/login", csrf_token=csrf(get("/login")), email=EMAIL, pin=user.pin)
step("login and services page", services["postgresql"].postgresql_db in page)

# import a dataset in the background
page, _url = post("/importer", csrf_token=csrf(page), dataset="flights")
task_id = re.search(r'data-task="([0-9a-f]{32})"', page)
if task_id is None:
    # the import was faster than the redirect
    step(
        "import: " + ("done" if "Flights was imported" in page else "no task"),
        "Flights was imported" in page,
    )
else:
    task = wait_for_task(task_id.group(1))
    step(f"import: {task['message']}", task["status"] == "done")

entry = services["postgresql"]
connection = psycopg2.connect(
    host=settings.postgresql_db_host,
    port=settings.postgresql_db_host_port,
    user=entry.postgresql_user,
    password=entry.postgresql_password,
    database=entry.postgresql_db,
)
with connection.cursor() as cursor:
    cursor.execute("SELECT count(*) FROM flights")
    rows = cursor.fetchone()[0]
connection.close()
step(f"rows in the table flights of the user: {rows}", rows > 0)
