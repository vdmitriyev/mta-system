import os

import pytest
from passlib.apache import HtpasswdFile

from app.services import (
    basic_auth,
    metabase_api,
    nifi_api,
    openrefine_api,
    pgadmin4_api,
    superset_api,
    wordpress_api,
)
from app.services.metabase_api import UserDataMetabase
from app.services.wordpress_api import UserDataWordpress


class FakeResponse:
    def __init__(self, status_code=200, data=None, content=b""):
        self.status_code = status_code
        self._data = data
        self.content = content

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


# ----- basic auth -----


def test_basic_auth_user_is_created_and_updated(settings):
    auth_file = basic_auth.port_auth_file(4001)
    assert auth_file.endswith("4001.htpasswd")

    assert basic_auth.set_basic_auth_user("common_user_01", "first", auth_file)
    assert HtpasswdFile(auth_file).check_password("common_user_01", "first")

    basic_auth.set_basic_auth_user("common_user_01", "second", auth_file)
    basic_auth.set_basic_auth_user("other", "pw", auth_file)
    htpasswd = HtpasswdFile(auth_file)
    assert htpasswd.check_password("common_user_01", "second")
    assert sorted(htpasswd.users()) == ["common_user_01", "other"]


def test_pgadmin4_login_goes_into_the_common_file(settings):
    assert pgadmin4_api.new_user_pgadmin4_for_web_auth("common_user_01", "pw")
    assert basic_auth.common_auth_file().endswith("common-basic-auth.db")
    assert HtpasswdFile(basic_auth.common_auth_file()).check_password(
        "common_user_01", "pw"
    )


# ----- OpenRefine and NiFi -----


def test_openrefine_container_and_login(settings, docker):
    user = openrefine_api.UserDataOpenRefine("common_user_01", "pw")
    assert openrefine_api.create_user_and_docker_or(user, 4001) is True

    run = docker.containers.runs[0]
    assert run["name"] == "openrefine-4001"
    assert run["image"] == f"openrefine:{openrefine_api.OPENREFINE_VERSION}"
    assert run["ports"] == {"80/tcp": ("127.0.0.1", 4001)}
    assert run["network"] == "mtas-network"
    assert HtpasswdFile(basic_auth.port_auth_file(4001)).check_password(
        "common_user_01", "pw"
    )


def test_openrefine_stops_without_docker(settings, no_docker):
    user = openrefine_api.UserDataOpenRefine("common_user_01", "pw")
    assert openrefine_api.create_user_and_docker_or(user, 4001) is False
    assert openrefine_api.create_docker_container(None) is False


def test_openrefine_stops_without_the_image(settings, docker):
    docker.images.missing.add(openrefine_api.IMAGE)
    user = openrefine_api.UserDataOpenRefine("common_user_01", "pw")
    assert openrefine_api.create_user_and_docker_or(user, 4001) is False
    assert docker.containers.runs == []
    assert not os.path.exists(basic_auth.port_auth_file(4001))


def test_metabase_stops_without_the_image(settings, docker, monkeypatch):
    docker.images.missing.add(metabase_api.IMAGE)
    monkeypatch.setattr(metabase_api.time, "sleep", pytest.fail)
    assert metabase_api.create_user_and_docker_mb(MB_USER, 3001) is False
    assert docker.containers.runs == []


def test_metabase_image_from_the_registry_is_used(settings, docker, monkeypatch):
    docker.images.missing.add(metabase_api.IMAGE)
    docker.images.in_registry.add(metabase_api.IMAGE)
    monkeypatch.setattr(metabase_api, "run_create_user", lambda *_args: True)
    assert metabase_api.create_user_and_docker_mb(MB_USER, 3001) is True
    assert docker.containers.runs[0]["image"] == "metabase/metabase:v0.57.3"


def test_nifi_container_and_login(settings, docker):
    user = nifi_api.UserDataNiFi("nifi_user_01", "pw")
    assert nifi_api.create_user_and_docker_nifi(user, 6001) is True

    run = docker.containers.runs[0]
    assert run["name"] == "nifi-6001"
    assert run["ports"] == {"8080/tcp": ("127.0.0.1", 6001)}
    assert run["environment"]["NIFI_WEB_PROXY_CONTEXT_PATH"] == "/nifi/6001/"
    assert HtpasswdFile(basic_auth.port_auth_file(6001)).check_password(
        "nifi_user_01", "pw"
    )


def test_nifi_without_docker(settings, no_docker):
    assert nifi_api.create_docker_container(6001) is False
    assert nifi_api.create_docker_container(None) is False


# ----- Metabase -----

MB_USER = UserDataMetabase("Jane", "Doe", "jane@x.org", "pw12345678")


def test_metabase_base_url(use_settings):
    use_settings()
    assert metabase_api.base_url_for(3001) == "http://localhost:3001"
    use_settings(METABASE_BASE_URL="http://metabase-")
    assert metabase_api.base_url_for(3001) == "http://metabase-3001"


def test_metabase_container_and_first_user(settings, docker, monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url))
        if len(calls) == 1:
            raise ConnectionError("not ready")
        return FakeResponse(data={"setup-token": "token-1"})

    def fake_post(url, json=None, **kwargs):
        calls.append(("POST", url, json))
        return FakeResponse(200)

    monkeypatch.setattr(metabase_api.requests, "get", fake_get)
    monkeypatch.setattr(metabase_api.requests, "post", fake_post)

    assert metabase_api.create_user_and_docker_mb(MB_USER, 3001) is True
    run = docker.containers.runs[0]
    assert run["name"] == "metabase-3001"
    assert run["image"] == f"metabase/metabase:{metabase_api.METABASE_VERSION}"
    assert run["ports"] == {"80/tcp": ("127.0.0.1", 3001)}

    method, url, payload = calls[-1]
    assert (method, url) == ("POST", "http://localhost:3001/api/setup")
    assert payload["token"] == "token-1"
    assert payload["user"]["email"] == "jane@x.org"
    assert payload["user"]["first_name"] == "Jane"


def test_metabase_that_never_starts(settings, docker, monkeypatch):
    attempts = []

    def fake_get(url, **kwargs):
        attempts.append(url)
        return FakeResponse(data=None)

    monkeypatch.setattr(metabase_api.requests, "get", fake_get)
    assert metabase_api.create_user_and_docker_mb(MB_USER, 3001) is False
    assert len(attempts) == settings.metabase_try_count
    assert metabase_api.create_docker_container(None) is False


def test_metabase_setup_that_fails(settings, monkeypatch):
    monkeypatch.setattr(
        metabase_api.requests, "post", lambda *a, **k: FakeResponse(400)
    )
    assert metabase_api.create_initialuser("http://x", MB_USER, "t") is False

    def broken(*_args, **_kwargs):
        raise ConnectionError("down")

    monkeypatch.setattr(metabase_api.requests, "post", broken)
    assert metabase_api.create_initialuser("http://x", MB_USER, "t") is False


# ----- WordPress -----

WP_USER = UserDataWordpress(
    wpLogin="wordpress_user_01",
    wpPassword="pw",
    wpEmail="u@x.org",
    databaseHost="mariadb",
    databaseName="mariadb_wordpress_db_7001",
    databaseUser="mariadb_user_01",
    databasePassword="dbpw",
    wordpressBaseURL="http://mtas.example.org/wordpress/",
)


def test_wordpress_containers(settings, docker, monkeypatch):
    pauses = []
    monkeypatch.setattr(wordpress_api.time, "sleep", pauses.append)

    assert wordpress_api.create_user_and_docker_wordpress(WP_USER, 7001) is True

    site, cli = docker.containers.runs
    assert site["name"] == "wordpress-7001"
    assert site["ports"] == {"80/tcp": ("127.0.0.1", 7001)}
    assert site["environment"]["WORDPRESS_DB_NAME"] == "mariadb_wordpress_db_7001"
    assert (
        "http://mtas.example.org/wordpress/7001/"
        in site["environment"]["WORDPRESS_CONFIG_EXTRA"]
    )
    assert site["volumes"] == cli["volumes"] == ["wordpress-7001:/var/www/html"]
    assert cli["name"] == "wordpress-cli-7001"
    assert "--admin_user=wordpress_user_01" in cli["command"]
    assert "--url=http://mtas.example.org/wordpress " in cli["command"]
    assert pauses == [wordpress_api.SLEEP_TIME_BETWEEN_CONTAINERS_SECONDS]
    assert ".htaccess" in docker.containers.items[0].commands[0][2]


def test_wordpress_without_docker(settings, no_docker):
    assert wordpress_api.create_user_and_docker_wordpress(WP_USER, 7001) is False
    assert wordpress_api.create_user_and_docker_wordpress(WP_USER, None) is False


# ----- Superset -----


class FakeSupersetSession:
    def __init__(self, users=None, login_page=b'<input id="csrf_token" value="tok">'):
        self.users = users or []
        self.login_page = login_page
        self.posts = []
        self.create_status = 200

    def get(self, url, **kwargs):
        if url.endswith("/login/"):
            return FakeResponse(content=self.login_page)
        return FakeResponse(data={"result": self.users})

    def post(self, url, data=None, **kwargs):
        self.posts.append((url, data, kwargs.get("headers")))
        return FakeResponse(self.create_status if url.endswith("/create") else 200)


@pytest.fixture
def superset(use_settings, monkeypatch):
    use_settings(
        SUPERSET_BASE_URL="http://superset:8088",
        SUPERSET_LOGIN="admin",
        SUPERSET_PASSWORD="admin-pw",
    )
    session = FakeSupersetSession()
    monkeypatch.setattr(superset_api.requests, "Session", lambda: session)
    return session


NEW_SUPERSET_USER = superset_api.SupersetUser(
    "bicourse_user_01", "pw", "jane.doe@x.org"
)


def test_superset_user_is_created(superset):
    client = superset_api.SupersetAPIClient(NEW_SUPERSET_USER)
    assert client.create_new_user() is True

    login, create = superset.posts
    assert login[1] == {
        "username": "admin",
        "password": "admin-pw",
        "csrf_token": "tok",
    }
    assert create[0] == "http://superset:8088/users/api/create"
    assert create[1]["username"] == "bicourse_user_01"
    assert (create[1]["first_name"], create[1]["last_name"]) == ("Jane", "Doe")
    assert create[2] == {"X-CSRFToken": "tok"}


def test_superset_user_that_exists_is_not_created_again(superset):
    superset.users = [{"email": "other@x.org", "username": "bicourse_user_01"}]
    assert superset_api.SupersetAPIClient(NEW_SUPERSET_USER).create_new_user() is True
    assert len(superset.posts) == 1


def test_superset_create_error(superset):
    superset.create_status = 500
    user = superset_api.SupersetUser("u", "pw", "single@x.org")
    assert superset_api.SupersetAPIClient(user).create_new_user() is False
    assert superset.posts[-1][1]["first_name"] == "Unknown"


def test_superset_without_csrf_token(superset):
    superset.login_page = b"<html></html>"
    assert superset_api.SupersetAPIClient(NEW_SUPERSET_USER).create_new_user() is False


def test_superset_login_error(superset):
    def broken(*_args, **_kwargs):
        raise superset_api.requests.RequestException("down")

    superset.post = broken
    assert superset_api.SupersetAPIClient(NEW_SUPERSET_USER).create_new_user() is False
