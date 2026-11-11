import re

import pytest

from app.models import BackgroundTask, Users
from app.routers.public import SESSION_CAPTCHA_KEY, login_limiter, registration_error
from app.security import make_hash
from app.users import find_user_by_email
from tests.conftest import COURSE_CODE, STUDENT_EMAIL, csrf_token, login, post

# ----- login -----


def test_login_with_email_and_pin(client, student):
    response = login(client)
    assert response.headers["location"] == "/services"
    assert client.get("/services").status_code == 200


def test_login_ignores_case_and_spaces_in_the_email(client, student):
    login(client, email=f"  {STUDENT_EMAIL.upper()} ")


@pytest.mark.parametrize(
    "email,pin", [(STUDENT_EMAIL, "0000"), ("nobody@uni.example", "1234"), ("", "")]
)
def test_login_with_wrong_data(client, student, email, pin):
    response = post(client, "/login", {"email": email, "pin": pin}, token_from="/login")
    assert response.status_code == 401
    assert "not correct" in response.text
    assert client.get("/services", follow_redirects=False).status_code == 303


def test_login_with_the_link_of_the_email(client, student):
    response = client.get(
        f"/login?uHash={student.url_hash}&pHash={student.pin_hash}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/services").status_code == 200


def test_login_with_a_wrong_link(client, student):
    response = client.get(f"/login?uHash={student.url_hash}&pHash=wrong")
    assert response.status_code == 401


def test_login_page_redirects_a_user_who_is_logged_in(student_client):
    response = student_client.get("/login", follow_redirects=False)
    assert response.headers["location"] == "/services"


def test_too_many_failed_logins_are_blocked(client, student):
    for _ in range(login_limiter.max_attempts):
        post(
            client,
            "/login",
            {"email": STUDENT_EMAIL, "pin": "0000"},
            token_from="/login",
        )
    response = post(
        client, "/login", {"email": STUDENT_EMAIL, "pin": "1234"}, token_from="/login"
    )
    assert response.status_code == 429
    assert "Too many" in response.text


def test_pages_for_users_redirect_guests_to_the_login(client):
    for path in ["/services", "/reviews", "/bonus", "/mtas-admin/"]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"] == "/login"


def test_deleted_or_inactive_user_is_logged_out(student_client, db, student):
    student.active = False
    db.commit()
    assert student_client.get("/services", follow_redirects=False).status_code == 303
    student.active, student.deleted = True, True
    db.commit()
    assert student_client.get("/services", follow_redirects=False).status_code == 303


def test_session_cookie_settings(client, student):
    response = login(client)
    cookie = response.headers["set-cookie"].lower()
    assert "mtas_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


# ----- registration -----


@pytest.fixture
def captcha(monkeypatch):
    """The captcha of the tests always shows 4321"""

    monkeypatch.setattr(
        "app.routers.public.generate_captcha",
        lambda add_noise=False: ("4321", "aW1hZ2U="),
    )
    return "4321"


def register(client, email="new.user@uni.example", code=COURSE_CODE, captcha="4321"):
    return post(
        client,
        "/register",
        {"email": email, "code": code, "captcha": captcha},
        token_from="/register",
    )


def test_registration_creates_the_user_in_the_background(client, db, captcha, no_email):
    response = register(client)
    assert response.status_code == 303
    status_url = response.headers["location"]
    assert re.fullmatch(r"/register/status/[0-9a-f]{32}", status_url)

    user = find_user_by_email(db, "new.user@uni.example")
    assert user is not None
    assert no_email[0]["to"] == "new.user@uni.example"

    page = client.get(status_url)
    assert page.status_code == 200
    assert "Registration complete" in page.text


def test_registration_accepts_code_in_any_case(client, db, captcha):
    assert register(client, code=COURSE_CODE.lower()).status_code == 303


def test_registration_of_a_known_email_sends_the_login_again(
    client, db, student, captcha, no_email
):
    response = register(client, email=STUDENT_EMAIL)
    assert db.query(Users).count() == 1
    assert no_email[0]["to"] == STUDENT_EMAIL
    assert "already registered" in client.get(response.headers["location"]).text


@pytest.mark.parametrize(
    "data,message",
    [
        ({"email": ""}, "Enter your e-mail"),
        ({"email": "not-an-email"}, "not valid"),
        ({"email": "new.user@other.org"}, "organization"),
        ({"code": "WRONG"}, "course code"),
        ({"captcha": "0000"}, "captcha"),
    ],
)
def test_registration_with_wrong_data(client, db, captcha, data, message):
    response = register(client, **data)
    assert response.status_code == 400
    assert message in response.text
    assert db.query(Users).count() == 0
    assert db.query(BackgroundTask).count() == 0


def test_captcha_is_valid_for_one_attempt(client, db, monkeypatch):
    texts = iter(["1111", "2222", "3333"])
    monkeypatch.setattr(
        "app.routers.public.generate_captcha",
        lambda add_noise=False: (next(texts), "aW1hZ2U="),
    )
    assert register(client, code="WRONG", captcha="1111").status_code == 400

    # the failed attempt used up the first captcha
    token = csrf_token(client, "/login")
    data = {"email": "a.b@uni.example", "code": COURSE_CODE, "csrf_token": token}
    response = client.post("/register", data={**data, "captcha": "1111"})
    assert response.status_code == 400
    assert "captcha" in response.text
    assert db.query(Users).count() == 0


def test_registration_error_checks(settings):
    good_hash = make_hash("4321", settings.hash_key_hidden.get_secret_value())
    assert registration_error("a.b@uni.example", COURSE_CODE, "4321", good_hash) is None
    assert "captcha" in registration_error("a.b@uni.example", COURSE_CODE, "4321", None)
    assert SESSION_CAPTCHA_KEY == "captcha"


def test_registration_page_shows_a_real_captcha(client):
    text = client.get("/register").text
    assert 'src="data:image/png;base64,' in text


def test_registration_that_fails_is_shown(client, db, captcha, monkeypatch):
    def broken(_db, _email):
        raise RuntimeError("database service is down")

    monkeypatch.setattr("app.routers.public.register_user_task", broken)
    response = register(client)
    page = client.get(response.headers["location"])
    assert "Registration not complete" in page.text
    assert "database service is down" not in page.text


def test_registration_status_that_is_still_running(client, db):
    db.add(BackgroundTask(public_id="a" * 32, kind="registration", status="running"))
    db.commit()
    page = client.get(f"/register/status/{'a' * 32}")
    assert "We set up your account" in page.text
    assert f'data-task="{"a" * 32}"' in page.text


def test_unknown_registration_status(client, db):
    db.add(BackgroundTask(public_id="b" * 32, kind="import:flights", status="done"))
    db.commit()
    assert client.get("/register/status/unknown").status_code == 404
    assert client.get(f"/register/status/{'b' * 32}").status_code == 404
