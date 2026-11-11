import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.app import create_app
from app.database import Base, get_engine
from tests.conftest import post


@pytest.mark.parametrize("path", ["/", "/index", "/about", "/login", "/register"])
def test_public_pages_answer(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "Test Course" in response.text


def test_static_files_are_served(client):
    assert client.get("/static/css/app.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/img/icons.svg").status_code == 200


def test_pages_have_security_headers(client):
    headers = client.get("/").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in headers["content-security-policy"]


def test_pages_have_no_inline_styles_or_scripts(client):
    """The Content-Security-Policy blocks them"""

    for path in ["/", "/about", "/login", "/register"]:
        text = client.get(path).text
        assert " style=" not in text
        assert "<style" not in text
        assert "onclick=" not in text


def test_home_shows_menu_for_guests(client):
    text = client.get("/").text
    assert 'href="/register"' in text
    assert 'href="/login"' in text
    assert 'href="/services"' not in text


def test_home_shows_menu_for_users(student_client):
    text = student_client.get("/").text
    assert 'href="/services"' in text
    assert 'href="/reviews"' in text
    assert 'href="/bonus"' in text
    assert "/mtas-admin/" not in text
    assert "Log out" in text


def test_unknown_page_is_404_html(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "Page not found" in response.text


def test_unknown_page_is_404_json_for_api_clients(client):
    response = client.get("/no-such-page", headers={"accept": "application/json"})
    assert response.status_code == 404
    assert response.json()["error"] == "page not found"


def test_post_without_csrf_token_is_rejected(client):
    response = client.post("/login", data={"email": "a@b.c", "pin": "1"})
    assert response.status_code == 403
    assert "expired" in response.text


def test_post_with_wrong_csrf_token_is_rejected(client):
    client.get("/login")
    response = client.post("/login", data={"email": "a@b.c", "csrf_token": "wrong"})
    assert response.status_code == 403


def test_wrong_method_is_405(client):
    assert client.post("/about").status_code == 405


def test_server_error_page_hides_details_in_production(use_settings, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.public.generate_captcha", broken)
    app = create_app(use_settings(TARGET_SERVER="production"))
    Base.metadata.create_all(get_engine())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/register")
    assert response.status_code == 500
    assert "Server error" in response.text
    assert "boom" not in response.text


def test_logout_needs_post(student_client):
    assert student_client.get("/logout").status_code == 405
    response = post(student_client, "/logout")
    assert response.status_code == 303
    assert student_client.get("/services", follow_redirects=False).status_code == 303


def test_theme_is_set_before_the_page_is_drawn(client):
    text = client.get("/about").text
    head = text[: text.index("</head>")]
    # theme.js without "defer": it runs before the page is drawn
    assert '<script src="/static/js/theme.js' in head
    assert f'theme.js?v={__version__}"></script>' in head
    assert "data-theme-toggle" in text
    assert client.get("/static/js/theme.js").status_code == 200


def test_theme_has_no_auto_mode():
    from app.config import BASE_DIR

    script = (BASE_DIR / "app/static/js/theme.js").read_text()
    assert '"light"' in script and '"dark"' in script
    assert "auto" not in script
    assert "auto" not in (BASE_DIR / "app/static/js/app.js").read_text()
