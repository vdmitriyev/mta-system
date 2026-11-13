import re

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
    assert re.search(r'theme\.js\?v=\d+"></script>', head)
    assert "data-theme-toggle" in text
    toggle = text[
        text.index("data-theme-toggle") : text.index(
            "</button>", text.index("data-theme-toggle")
        )
    ]
    assert re.search(r"icons\.svg\?v=\w+#sun", toggle)
    assert re.search(r"icons\.svg\?v=\w+#moon", toggle)
    assert "Theme" not in toggle
    assert client.get("/static/js/theme.js").status_code == 200


def test_theme_has_no_auto_mode():
    from app.config import BASE_DIR

    script = (BASE_DIR / "app/static/js/theme.js").read_text()
    assert '"light"' in script and '"dark"' in script
    assert "auto" not in script
    assert "auto" not in (BASE_DIR / "app/static/js/app.js").read_text()


def test_about_page_shows_the_versions_of_versions_env(client, use_settings):
    from app.config import read_versions

    versions = read_versions()
    text = client.get("/about").text
    for key in ("PGADMIN4", "POSTGRESQL", "METABASE", "OPENREFINE", "MARIADB"):
        assert f'<span class="badge info">{versions[key + "_VERSION"]}</span>' in text
    assert "15.14" not in text and "9.9<" not in text

    use_settings(OPENREFINE_VERSION="3.11.0")
    assert '<span class="badge info">3.11.0</span>' in client.get("/about").text


def test_about_page_marks_deprecated_services(client):
    text = client.get("/about").text
    start = text.index("<h3>Apache NiFi</h3>")
    card = text[start : text.index("</article>", start)]
    assert "deprecated" in card and "badge info" not in card


def test_about_page_shows_mariadb_and_wordpress(client):
    from app.config import read_versions

    text = client.get("/about").text
    for name, version in (
        ("MariaDB", read_versions()["MARIADB_VERSION"]),
        ("WordPress", read_versions()["WORDPRESS_VERSION"]),
    ):
        start = text.index(f"<h3>{name}</h3>")
        card = text[text.rindex("<article", 0, start) : text.index("</article>", start)]
        assert f'src="/static/img/{name.lower()}-logo.svg"' in card
        assert f'<span class="badge info">{version}</span>' in card
        assert "supported" in card


def test_about_page_names_jupyterhub(client):
    text = client.get("/about").text
    assert "<h3>JupyterHub</h3>" in text
    assert "Jupyter Notebooks for Python in a browser." in text
    assert "Jupyter Notebook (JupyterHub)" not in text


def test_main_keeps_its_space_above_and_below():
    from app.config import BASE_DIR

    css = (BASE_DIR / "app/static/css/app.css").read_text()
    container = css[
        css.index(".container {") : css.index("}", css.index(".container {"))
    ]
    # "padding: 0 ..." would remove the space of <main> above and below the content
    assert "padding-inline:" in container and "padding:" not in container


def test_index_cards_are_centred(student_client):
    text = student_client.get("/").text
    assert '<div class="card-row">' in text
    # the welcome text is centred together with the cards
    assert text.index('<div class="welcome">') < text.index("Welcome back")


def test_header_shows_a_gear_instead_of_the_email(student_client):
    text = student_client.get("/").text
    header = text[text.index('<header class="site-header">') : text.index("</header>")]
    assert "user-email" not in header
    assert 'href="/account"' in header
    # versioned address: browsers do not use an old icons.svg without the gear
    assert re.search(r'icons\.svg\?v=\w+#gear"', header)
    assert 'title="Log out sam.student@uni.example"' in header
    # order: theme, gear, (admin), log out
    assert header.index("data-theme-toggle") < header.index('href="/account"')
    assert header.index('href="/account"') < header.index('action="/logout"')


def test_header_order_for_admins(admin_client):
    text = admin_client.get("/").text
    header = text[text.index('<header class="site-header">') : text.index("</header>")]
    positions = [
        header.index("data-theme-toggle"),
        header.index('href="/account"'),
        header.index('href="/mtas-admin/"'),
        header.index('action="/logout"'),
    ]
    assert positions == sorted(positions)


def test_account_page_shows_the_registration_email(student_client):
    response = student_client.get("/account")
    assert response.status_code == 200
    assert "Registration e-mail" in response.text
    assert "<dd>sam.student@uni.example</dd>" in response.text


def test_account_page_needs_a_login(client):
    response = client.get("/account", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/login" in response.headers["location"]


def test_login_page_layout(client):
    text = client.get("/login").text
    assert "No account? Register" not in text
    assert '<input class="input" type="password" id="pin"' in text
    assert '<p class="muted small login-hint">Hint: Lost your PIN?' in text
