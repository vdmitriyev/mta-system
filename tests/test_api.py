from fastapi.testclient import TestClient

from app.app import create_app
from app.database import Base, get_engine
from app.models import BackgroundTask, MetabaseService
from tests.conftest import login


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"]


def test_task_state(client, db):
    db.add(BackgroundTask(public_id="d" * 32, kind="registration", status="running"))
    db.commit()
    assert client.get(f"/api/tasks/{'d' * 32}").json() == {
        "id": "d" * 32,
        "kind": "registration",
        "status": "running",
        "message": None,
        "finished": False,
    }


def test_unknown_task_is_404_json(client):
    response = client.get("/api/tasks/unknown")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_services_status_needs_login(client):
    response = client.get("/api/services/status")
    assert response.status_code == 401
    assert response.json()["error"] == "login needed"


def test_services_status(student_client, db, student, docker):
    db.add(
        MetabaseService(
            user_id=student.itid,
            metabase_login="x",
            metabase_password="y",
            metabase_docker_port=3001,
        )
    )
    db.commit()
    docker.containers.add("metabase-3001", "running")
    assert student_client.get("/api/services/status").json() == {"metabase": "running"}


def test_api_docs_are_on_in_development(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/api/health",
        "/api/tasks/{task_id}",
        "/api/services/status",
    }
    assert "content-security-policy" not in client.get("/docs").headers
    assert 'href="/docs"' in client.get("/").text


def production_client(use_settings, **overrides):
    app = create_app(
        use_settings(
            TARGET_SERVER="production", SESSION_COOKIE_SECURE="false", **overrides
        )
    )
    Base.metadata.create_all(get_engine())
    return TestClient(app)


def test_api_docs_are_off_in_production(use_settings):
    with production_client(use_settings) as client:
        for path in ["/docs", "/redoc", "/openapi.json"]:
            assert client.get(path).status_code == 404, path
        assert client.get("/api/health").status_code == 200
        assert 'href="/docs"' not in client.get("/").text


def test_api_docs_can_be_switched_on_in_production(use_settings):
    with production_client(use_settings, ENABLE_API_DOCS="true") as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_api_docs_can_be_switched_off_in_development(use_settings):
    app = create_app(use_settings(ENABLE_API_DOCS="false"))
    Base.metadata.create_all(get_engine())
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_session_cookie_is_secure_in_production(use_settings):
    from app.database import session_scope
    from tests.conftest import add_user, csrf_token

    app = create_app(use_settings(TARGET_SERVER="production"))
    Base.metadata.create_all(get_engine())
    with TestClient(app, base_url="https://testserver") as client:
        with session_scope() as db:
            add_user(db)
        response = login(client)
        assert "secure" in response.headers["set-cookie"].lower()
        assert csrf_token(client)
