import re

import pytest
from docker.errors import ImageNotFound, NotFound
from fastapi.testclient import TestClient

from app import config
from app.app import create_app
from app.config import Settings, set_settings
from app.database import Base, get_engine, session_scope
from app.models import Exercises, PostgreSQLService, Users
from app.routers.public import login_limiter
from app.service_settings import set_creates_accounts
from app.users import email_hash, pin_hash

ADMIN_EMAIL = "ada.admin@uni.example"
STUDENT_EMAIL = "sam.student@uni.example"
COURSE_CODE = "BI2026"

BASE_ENV = {
    "TARGET_SERVER": "development",
    "SECRET_KEY": "test-secret-key-test-secret-key",
    "HASH_KEY_HIDDEN": "test-hash-key-hidden",
    "HASH_KEY_LINKS": "test-hash-key-links",
    "COURSE_SECURITY_CODE": COURSE_CODE,
    "COURSE_NAME_TITLE": "Test Course",
    "SERVER_FQDN": "mtas.example.org",
    "SYSTEM_ADMINS": ADMIN_EMAIL,
    "ALLOWED_FQDN_FOR_EMAILS": "uni.example",
    "METABASE_TRY_SLEEP_SEC": "0",
}


def make_settings(tmp_path, **overrides) -> Settings:
    env = dict(BASE_ENV)
    env["MTAS_DB_PATH"] = str(tmp_path / "test.db")
    env["NGINX_BASIC_AUTH_DIR_ABSOLUTE"] = str(tmp_path / "htpasswd")
    env.update(overrides)
    return Settings.from_env(env)


@pytest.fixture
def settings(tmp_path):
    """Settings of the tests. The services for the students are switched off."""

    settings = make_settings(tmp_path)
    set_settings(settings)
    yield settings
    set_settings(None)


@pytest.fixture
def use_settings(tmp_path):
    """Replaces the settings: use_settings(MAIL_USERNAME="mailer")"""

    def apply(**overrides):
        settings = make_settings(tmp_path, **overrides)
        set_settings(settings)
        return settings

    yield apply
    set_settings(None)


@pytest.fixture
def app(settings):
    app = create_app(settings)
    Base.metadata.create_all(get_engine())
    login_limiter.reset()
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def db(app):
    with session_scope() as session:
        yield session


@pytest.fixture(autouse=True)
def no_email(monkeypatch):
    """Collects the e-mails instead of sending them"""

    sent = []

    def fake_send_email(to_email, subject, content, settings):
        sent.append({"to": to_email, "subject": subject, "content": content})
        return True

    monkeypatch.setattr("app.users.send_email", fake_send_email)
    return sent


def switch_on(db, *services):
    """Lets the app create accounts in these services (admin page "Auto creation")"""

    for service in services:
        set_creates_accounts(db, service, True)


def force_on(db, *services):
    """Writes "on" into the database, also for deprecated services (as before 2.3.0)"""

    from app.models import ServiceSettings
    from app.service_settings import add_default_service_settings

    add_default_service_settings(db)
    db.query(ServiceSettings).filter(ServiceSettings.service.in_(services)).update(
        {"create_accounts": True}
    )
    db.commit()


def add_user(db, email=STUDENT_EMAIL, pin="1234", number=1, assigned=True) -> Users:
    user = Users(
        email=email,
        internal_email=f"{config.POSTGRESQL_USER_PREFIX}_{str(number).zfill(2)}@mtas.example.org",
        url_hash=email_hash(email),
        pin=pin,
        pin_hash=pin_hash(pin),
        course_code=COURSE_CODE,
        is_user_assigned=assigned,
    )
    db.add(user)
    db.commit()
    return user


def add_postgresql(db, user, number=1) -> PostgreSQLService:
    entry = PostgreSQLService(
        user_id=user.itid,
        postgresql_db=f"bicourse_db_{str(number).zfill(2)}",
        postgresql_user=f"bicourse_user_{str(number).zfill(2)}",
        postgresql_password="pg-secret-11",
        created=True,
    )
    db.add(entry)
    db.commit()
    return entry


def add_exercise(db, code="EX1", name="Exercise 1", order=1, **values) -> Exercises:
    values.setdefault("has_review", True)
    values.setdefault("has_bonus", True)
    values.setdefault("bonus_max_points", 5.0)
    exercise = Exercises(code=code, name=name, exercise_order=order, **values)
    db.add(exercise)
    db.commit()
    return exercise


def csrf_token(client, path="/login") -> str:
    """Gets the CSRF token from a form of the page"""

    response = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match, f"no CSRF token on {path}"
    return match.group(1)


def post(client, path, data=None, token_from="/about", **kwargs):
    """POST request with the CSRF token of the session"""

    data = dict(data or {})
    data["csrf_token"] = csrf_token(client, token_from)
    return client.post(path, data=data, follow_redirects=False, **kwargs)


def login(client, email=STUDENT_EMAIL, pin="1234"):
    response = post(client, "/login", {"email": email, "pin": pin}, token_from="/login")
    assert response.status_code == 303, response.text
    return response


@pytest.fixture
def student(db):
    return add_user(db)


@pytest.fixture
def admin(db):
    return add_user(db, email=ADMIN_EMAIL, pin="9999", number=2)


@pytest.fixture
def student_client(client, student):
    login(client)
    return client


@pytest.fixture
def admin_client(client, admin):
    login(client, email=ADMIN_EMAIL, pin="9999")
    return client


class FakeImage:
    def __init__(self, tags):
        self.tags = tags
        self.short_id = "sha256:abc"


class FakeContainer:
    def __init__(self, name, status="running", logs=b"line 1\nline 2\n"):
        self.name = name
        self.status = status
        self.short_id = f"id-{name}"[:12]
        self.id = f"long-id-{name}"
        self.image = FakeImage([f"{name.split('-')[0]}:latest"])
        self._logs = logs
        self.commands = []

    def logs(self, tail=20):
        return self._logs

    def start(self):
        self.status = "running"

    def stop(self):
        self.status = "exited"

    def rename(self, new_name):
        self.name = new_name

    def exec_run(self, command):
        self.commands.append(command)


class FakeContainers:
    def __init__(self):
        self.items = []
        self.runs = []

    def add(self, name, status="running", **kwargs):
        container = FakeContainer(name, status, **kwargs)
        self.items.append(container)
        return container

    def list(self, all=False):
        return [c for c in self.items if all or c.status == "running"]

    def get(self, name):
        for container in self.items:
            if container.name == name or container.id == name:
                return container
        raise LookupError(f"No such container: {name}")

    def run(self, **kwargs):
        self.runs.append(kwargs)
        return self.add(kwargs["name"])


class FakeImages:
    """All images are on the server, except the ones in "missing" """

    def __init__(self):
        self.missing = set()
        self.in_registry = set()

    def get(self, name):
        if name in self.missing:
            raise ImageNotFound(f"No such image: {name}")
        return FakeImage([name])

    def get_registry_data(self, name):
        if name not in self.in_registry:
            raise NotFound(f"manifest unknown: {name}")
        return {"name": name}


class FakeDocker:
    def __init__(self):
        self.containers = FakeContainers()
        self.images = FakeImages()


@pytest.fixture
def docker(monkeypatch):
    """Docker daemon of the tests: starts no real containers"""

    fake = FakeDocker()
    monkeypatch.setattr("app.services.docker_ctl.get_client", lambda: fake)
    return fake


@pytest.fixture
def no_docker(monkeypatch):
    def fail():
        raise OSError("no docker socket")

    monkeypatch.setattr("app.services.docker_ctl.get_client", fail)
