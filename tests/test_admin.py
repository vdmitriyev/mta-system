import os

import pytest
import requests

from app.models import (
    BackgroundTask,
    ExerciseBonusPoints,
    ExerciseReviews,
    MetabaseService,
    OpenRefineService,
    Users,
)
from app.routers import admin as admin_router
from app.routers.admin import (
    account_number,
    check_basic_auth,
    create_service_task,
    grouped_settings,
)
from app.tasks import TaskError
from app.visibility import ui_visibility_settings
from tests.conftest import STUDENT_EMAIL, add_exercise, add_postgresql, add_user, post

ADMIN_PAGES = [
    "/mtas-admin/",
    "/mtas-admin/users",
    "/mtas-admin/reviews",
    "/mtas-admin/bonus",
    "/mtas-admin/services/metabase",
    "/mtas-admin/services/openrefine",
    "/mtas-admin/services/openrefine?check=access",
    "/mtas-admin/auto-creation",
    "/mtas-admin/monitoring",
    "/mtas-admin/visibility",
    "/mtas-admin/settings",
]


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_pages_answer(admin_client, no_docker, path):
    response = admin_client.get(path)
    assert response.status_code == 200
    assert " style=" not in response.text


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_pages_are_forbidden_for_users(student_client, path):
    response = student_client.get(path)
    assert response.status_code == 403
    assert "No access" in response.text


def test_admin_actions_are_forbidden_for_users(student_client, db):
    for path in [
        "/mtas-admin/accounts/generate",
        "/mtas-admin/visibility",
        "/mtas-admin/services/metabase/start",
    ]:
        assert (
            post(
                student_client,
                path,
                {"ui_key": "bonus", "visible": "false", "user_id": 1},
            ).status_code
            == 403
        )
    assert db.query(BackgroundTask).count() == 0
    assert ui_visibility_settings(db)["bonus"] is True


def test_admin_link_is_in_the_menu_of_admins_only(admin_client):
    assert 'href="/mtas-admin/"' in admin_client.get("/").text


# ----- overview and users -----


def test_overview_counts_users_and_services(admin_client, db, admin, student):
    add_user(db, email="tmp.generated0@localhost.lc", number=5, assigned=False)
    add_postgresql(db, student)
    db.add(
        BackgroundTask(
            public_id="e" * 32,
            kind="registration",
            status="failed",
            message="Something failed",
        )
    )
    db.commit()

    text = admin_client.get("/mtas-admin/").text.replace("\n", "")
    assert '<div class="value">2</div><div class="label">Registered users</div>' in text
    assert (
        '<div class="value">1</div><div class="label">Prepared accounts (free)</div>'
        in text
    )
    assert (
        '<div class="value">1</div><div class="label">postgresql accounts</div>' in text
    )
    assert "Something failed" in text


def test_generate_accounts(admin_client, db, admin, monkeypatch):
    monkeypatch.setattr("app.users.time.sleep", lambda _seconds: None)
    response = post(admin_client, "/mtas-admin/accounts/generate")
    assert response.headers["location"] == "/mtas-admin/"

    prepared = db.query(Users).filter(Users.is_user_assigned.is_(False)).count()
    assert prepared == 5
    task = db.query(BackgroundTask).one()
    assert (task.kind, task.status, task.message) == (
        "accounts:generate",
        "done",
        "Prepared accounts: 5",
    )
    assert "5 accounts are prepared" in admin_client.get("/mtas-admin/").text


def test_users_page(admin_client, db, admin, student):
    add_postgresql(db, student)
    text = admin_client.get("/mtas-admin/users").text
    assert STUDENT_EMAIL in text
    assert "Sam Student" in text
    assert f"uHash={student.url_hash}&amp;pHash={student.pin_hash}" in text
    assert "postgresql" in text


# ----- reviews -----


def test_reviews_overview(admin_client, db, admin, student):
    exercise = add_exercise(db, "EX1", "Data model")
    add_exercise(db, "EX2", "No review", order=2, has_review=False)
    db.add(
        ExerciseReviews(
            user_id=student.itid,
            exercise_id=exercise.itid,
            content="ok",
            submitted=True,
        )
    )
    db.commit()

    text = admin_client.get("/mtas-admin/reviews").text
    assert ">EX1<" in text and ">EX2<" not in text
    assert f"/mtas-admin/reviews/edit?user={student.itid}&amp;exercise=EX1" in text
    assert "text yes, submitted yes, reviewed no" in text


def test_reviews_overview_without_exercises(admin_client):
    assert (
        "no exercises with a review part"
        in admin_client.get("/mtas-admin/reviews").text
    )


def test_edit_review(admin_client, db, admin, student):
    add_exercise(db, "EX1", "Data model")
    url = f"/mtas-admin/reviews/edit?user={student.itid}&exercise=EX1"
    page = admin_client.get(url)
    assert page.status_code == 200
    assert "No review is saved yet" in page.text
    assert page.text.count("checked") == 3

    response = post(
        admin_client,
        "/mtas-admin/reviews/edit",
        {
            "user": student.itid,
            "exercise": "EX1",
            "content": "# Good\n<b>x</b>",
            "submitted": "on",
            "visible": "on",
        },
    )
    assert response.headers["location"] == url

    review = db.query(ExerciseReviews).one()
    assert (review.submitted, review.reviewed, review.visible) == (True, False, True)
    assert review.user_id == student.itid

    page = admin_client.get(url)
    assert "The review was saved" in page.text
    assert "<h1>Good</h1>" in page.text
    assert "# Good" in page.text
    assert page.text.count("checked") == 2


def test_each_save_adds_a_review_row(admin_client, db, admin, student):
    add_exercise(db, "EX1")
    for content in ("first", "second"):
        post(
            admin_client,
            "/mtas-admin/reviews/edit",
            {"user": student.itid, "exercise": "EX1", "content": content},
        )
    assert db.query(ExerciseReviews).count() == 2
    assert (
        "second"
        in admin_client.get(
            f"/mtas-admin/reviews/edit?user={student.itid}&exercise=EX1"
        ).text
    )


@pytest.mark.parametrize("kind", ["reviews", "bonus"])
def test_edit_pages_for_unknown_user_or_exercise(
    admin_client, db, admin, student, kind
):
    add_exercise(db, "EX1")
    assert (
        admin_client.get(f"/mtas-admin/{kind}/edit?user=999&exercise=EX1").status_code
        == 404
    )
    assert (
        admin_client.get(
            f"/mtas-admin/{kind}/edit?user={student.itid}&exercise=NONE"
        ).status_code
        == 404
    )
    assert (
        admin_client.get(f"/mtas-admin/{kind}/edit?user=abc&exercise=EX1").status_code
        == 400
    )
    assert admin_client.get(f"/mtas-admin/{kind}/edit").status_code == 400
    data = {"user": 999, "exercise": "EX1", "points": "1"}
    assert post(admin_client, f"/mtas-admin/{kind}/edit", data).status_code == 404
    data = {"user": student.itid, "exercise": "NONE", "points": "1"}
    assert post(admin_client, f"/mtas-admin/{kind}/edit", data).status_code == 404


# ----- bonus points -----


def test_bonus_overview(admin_client, db, admin, student):
    first = add_exercise(db, "EX1", "Data model")
    second = add_exercise(db, "EX2", "ETL", order=2)
    db.add(
        ExerciseBonusPoints(user_id=student.itid, exercise_id=first.itid, points=4.0)
    )
    db.add(
        ExerciseBonusPoints(
            user_id=student.itid, exercise_id=second.itid, points=2.0, is_addable=False
        )
    )
    db.commit()

    text = admin_client.get("/mtas-admin/bonus").text
    assert "<strong>4.0</strong>" in text
    assert '<span class="struck">2.0</span>' in text
    assert f"/mtas-admin/bonus/edit?user={student.itid}&amp;exercise=EX2" in text


def test_bonus_overview_without_exercises(admin_client):
    assert (
        "no exercises with a bonus part" in admin_client.get("/mtas-admin/bonus").text
    )


def test_edit_bonus_points(admin_client, db, admin, student):
    add_exercise(db, "EX1", bonus_max_points=5.0)
    url = f"/mtas-admin/bonus/edit?user={student.itid}&exercise=EX1"
    assert 'value="5.0"' in admin_client.get(url).text

    response = post(
        admin_client,
        "/mtas-admin/bonus/edit",
        {"user": student.itid, "exercise": "EX1", "points": "3,5", "visible": "on"},
    )
    assert response.headers["location"] == url
    entry = db.query(ExerciseBonusPoints).one()
    assert (entry.points, entry.visible, entry.is_addable) == (3.5, True, False)
    assert 'value="3.5"' in admin_client.get(url).text


def test_bonus_points_must_be_a_number(admin_client, db, admin, student):
    add_exercise(db, "EX1")
    response = post(
        admin_client,
        "/mtas-admin/bonus/edit",
        {"user": student.itid, "exercise": "EX1", "points": "many"},
    )
    assert response.status_code == 400
    assert "as a number" in response.text
    assert db.query(ExerciseBonusPoints).count() == 0


# ----- containers of the users -----


def add_metabase(db, user, port=3001, **values):
    entry = MetabaseService(
        user_id=user.itid,
        metabase_login="x",
        metabase_password="mb-pw",
        metabase_docker_port=port,
        **values,
    )
    db.add(entry)
    db.commit()
    return entry


def test_service_page_shows_accounts_and_states(
    admin_client, db, admin, student, docker
):
    add_metabase(db, student, created=True)
    docker.containers.add("metabase-3001", "exited")

    text = admin_client.get("/mtas-admin/services/metabase").text
    assert "Metabase containers" in text
    assert "<code>metabase-3001</code>" in text
    assert '<span class="badge danger">exited</span>' in text
    assert '<span class="badge success">created</span>' in text
    assert '<span class="badge">none</span>' in text


def test_unknown_service_page_is_404(admin_client):
    assert admin_client.get("/mtas-admin/services/nifi").status_code == 404
    assert (
        post(
            admin_client, "/mtas-admin/services/nifi/start", {"user_id": 1}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("action,status", [("start", "running"), ("stop", "exited")])
def test_start_and_stop_a_container(
    admin_client, db, admin, student, docker, action, status
):
    add_metabase(db, student)
    container = docker.containers.add("metabase-3001", "created")

    response = post(
        admin_client,
        f"/mtas-admin/services/metabase/{action}",
        {"user_id": student.itid},
    )
    assert response.headers["location"] == "/mtas-admin/services/metabase"
    assert container.status == status
    assert (
        f"{action} was sent" in admin_client.get("/mtas-admin/services/metabase").text
    )


def test_action_without_container_fails(admin_client, db, admin, student, docker):
    post(
        admin_client, "/mtas-admin/services/openrefine/start", {"user_id": student.itid}
    )
    assert "start failed" in admin_client.get("/mtas-admin/services/openrefine").text


def test_unknown_action_or_user(admin_client, db, admin, student, docker):
    assert (
        post(
            admin_client,
            "/mtas-admin/services/metabase/remove",
            {"user_id": student.itid},
        ).status_code
        == 404
    )
    assert (
        post(
            admin_client, "/mtas-admin/services/metabase/start", {"user_id": 999}
        ).status_code
        == 404
    )
    assert (
        post(admin_client, "/mtas-admin/services/metabase/start", {}).status_code == 400
    )


def test_create_metabase_again(admin_client, db, admin, student, docker, monkeypatch):
    add_postgresql(db, student)
    add_metabase(db, student, created=True)
    old_container = docker.containers.add("metabase-3001", "running")
    seen = []
    monkeypatch.setattr(
        "app.provisioning.metabase_api.create_user_and_docker_mb",
        lambda data, port: seen.append((data.email, data.password, port)) or True,
    )

    response = post(
        admin_client, "/mtas-admin/services/metabase/create", {"user_id": student.itid}
    )
    assert response.headers["location"] == "/mtas-admin/services/metabase"

    assert seen == [(student.internal_email, "pg-secret-11", 3001)]
    assert (
        old_container.name.startswith("metabase-3001-")
        and old_container.status == "exited"
    )
    rows = db.query(MetabaseService).order_by(MetabaseService.itid).all()
    assert [(row.deleted, row.created) for row in rows] == [
        (True, False),
        (False, True),
    ]
    task = db.query(BackgroundTask).one()
    assert (task.kind, task.status) == ("service:create:metabase", "done")
    assert STUDENT_EMAIL in task.message


def test_create_openrefine_without_postgresql(db, admin, student, docker, settings):
    message = create_service_task(db, "openrefine", student.itid)
    assert "OpenRefine was created" in message
    entry = db.query(OpenRefineService).one()
    assert (entry.openrefine_user, entry.openrefine_docker_port, entry.created) == (
        "common_user_01",
        4001,
        True,
    )
    assert len(entry.openrefine_password) == 10
    assert docker.containers.runs[0]["name"] == "openrefine-4001"


def test_create_service_keeps_the_old_password(db, student, docker, monkeypatch):
    add_metabase(db, student)
    seen = []
    monkeypatch.setattr(
        "app.provisioning.metabase_api.create_user_and_docker_mb",
        lambda data, port: seen.append(data.password) or False,
    )
    with pytest.raises(TaskError, match="was not created"):
        create_service_task(db, "metabase", student.itid)
    assert seen == ["mb-pw"]


def test_create_service_errors(db, student, docker):
    with pytest.raises(TaskError, match="No such user"):
        create_service_task(db, "metabase", 999)
    student.internal_email = "custom@mtas.example.org"
    db.commit()
    with pytest.raises(TaskError, match="no number"):
        create_service_task(db, "metabase", student.itid)


def test_account_number(db, student):
    assert account_number(student) == 1
    student.internal_email = "bicourse_user_123@x.org"
    assert account_number(student) == 123


# ----- server -----


def test_monitoring_page(admin_client, docker):
    docker.containers.add(
        "metabase-3001", "running", logs=b"<script>alert(1)</script> started\n"
    )
    docker.containers.add("nifi-6001", "exited")

    text = admin_client.get("/mtas-admin/monitoring").text
    assert "metabase-3001" in text and "nifi-6001" in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt; started" in text
    assert "<script>alert(1)" not in text
    assert "Containers running" in text


def test_server_summary(no_docker):
    summary = admin_router.server_summary()
    assert summary["containers"] == {"total": 0, "running": 0, "exited": 0}
    assert 0 <= summary["memory_percent"] <= 100
    assert summary["memory_total_mb"] > 0


def test_settings_page_hides_secrets(admin_client, settings):
    text = admin_client.get("/mtas-admin/settings").text
    assert "<title>Settings" in text
    assert 'href="/mtas-admin/settings" aria-current="page">Settings</a>' in text
    assert "SERVER_FQDN" in text and "mtas.example.org" in text
    assert "METABASE_PORT_OFFSET" in text
    for secret in (
        settings.secret_key.get_secret_value(),
        "test-hash-key",
        "PASSWORD",
        "sqlite://",
    ):
        assert secret not in text


def test_grouped_settings(settings):
    groups = grouped_settings()
    assert list(groups)[0] == "GENERAL"
    assert ("POSTGRESQL_DB_HOST", "localhost") in groups["POSTGRESQL"]
    assert "NAMES AND PORTS" not in groups
    # names and ports are in the block of their service
    assert ("NIFI_PORT_OFFSET", 6000) in groups["NIFI"]
    assert ("POSTGRESQL_DB_PREFIX", "bicourse_db") in groups["POSTGRESQL"]
    assert ("JUPYTERHUB_USER_PREFIX", "jh_user") in groups["JUPYTERHUB"]
    assert ("METABASE_PORT_OFFSET", 3000) in groups["METABASE"]


def test_change_visibility(admin_client, db):
    assert ui_visibility_settings(db)["bonus"] is True
    response = post(
        admin_client, "/mtas-admin/visibility", {"ui_key": "bonus", "visible": "false"}
    )
    assert response.headers["location"] == "/mtas-admin/visibility"
    assert ui_visibility_settings(db)["bonus"] is False

    text = admin_client.get("/mtas-admin/visibility").text
    assert "is now hidden" in text
    assert 'href="/bonus"' not in text

    post(admin_client, "/mtas-admin/visibility", {"ui_key": "bonus", "visible": "true"})
    assert ui_visibility_settings(db)["bonus"] is True


def test_change_visibility_of_an_unknown_key(admin_client):
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "<b>x</b>", "visible": "true"},
    )
    text = admin_client.get("/mtas-admin/visibility").text
    assert "There is no setting" in text
    assert "<b>x</b>" not in text
    assert (
        post(
            admin_client,
            "/mtas-admin/visibility",
            {"ui_key": "bonus", "visible": "maybe"},
        ).status_code
        == 400
    )


class FakeResponse:
    status_code = 200


def test_access_check_on_the_openrefine_page(
    admin_client, db, admin, student, docker, monkeypatch
):
    db.add(
        OpenRefineService(
            user_id=student.itid,
            openrefine_user="common_user_01",
            openrefine_password="pw",
            openrefine_docker_port=4001,
        )
    )
    other = add_user(db, email="other@uni.example", number=3)
    db.add(
        OpenRefineService(
            user_id=other.itid,
            openrefine_user="common_user_03",
            openrefine_password="pw",
            openrefine_docker_port=None,
        )
    )
    db.commit()
    calls = []

    def fake_get(url, auth=None, **kwargs):
        calls.append((url, auth))
        return FakeResponse()

    monkeypatch.setattr(admin_router.requests, "get", fake_get)
    text = admin_client.get("/mtas-admin/services/openrefine").text
    assert "Check access" in text and "<th data-sort" in text
    assert calls == []

    text = admin_client.get("/mtas-admin/services/openrefine?check=access").text

    assert calls == [
        ("https://mtas.example.org/openrefine/4001/", ("common_user_01", "pw"))
    ]
    assert '<span class="badge success">200</span>' in text
    assert "NO PORT" in text and "NO SERVICE" in text


@pytest.mark.parametrize(
    "error,verdict",
    [
        (requests.exceptions.Timeout(), "TIMEOUT"),
        (requests.exceptions.ConnectionError(), "DOWN"),
        (RuntimeError("x"), "ERROR"),
    ],
)
def test_check_basic_auth_errors(monkeypatch, error, verdict):
    def broken(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(admin_router.requests, "get", broken)
    assert check_basic_auth("https://x/", "u", "p") == verdict


def test_old_access_check_address_leads_to_openrefine(admin_client):
    response = admin_client.get("/mtas-admin/basic-auth-check", follow_redirects=False)
    assert (
        response.headers["location"] == "/mtas-admin/services/openrefine?check=access"
    )


def test_metabase_page_has_no_access_check(admin_client, docker):
    text = admin_client.get("/mtas-admin/services/metabase").text
    assert "Check access" not in text
    assert (
        "Image is on this server: <strong><code>metabase/metabase:v0.57.3</code></strong>"
        in text
    )
    assert "docker pull" not in text


def test_service_page_warns_about_a_missing_image(admin_client, docker):
    docker.images.missing.add("openrefine:3.10.1")
    text = admin_client.get("/mtas-admin/services/openrefine").text
    assert (
        "Image is not on this server: <strong><code>openrefine:3.10.1</code></strong>"
        in text
    )
    assert "<p>Build it on the server:</p>" in text
    assert (
        '<pre class="command"><code>docker build --build-arg OPENREFINE_VERSION=3.10.1 '
        "-t openrefine:3.10.1 provision/openrefine</code></pre>" in text
    )


def test_create_again_keeps_the_old_container_without_image(db, student, docker):
    old = docker.containers.add("openrefine-4001", "running")
    docker.images.missing.add("openrefine:3.10.1")
    with pytest.raises(TaskError, match="not on this server and not in the registry"):
        create_service_task(db, "openrefine", student.itid)
    assert (old.name, old.status) == ("openrefine-4001", "running")
    assert docker.containers.runs == []


def test_services_menu(admin_client, docker):
    text = admin_client.get("/mtas-admin/services/metabase").text
    menu = text[text.index("<details") : text.index("</details>")]
    assert '<summary aria-current="page">Services' in menu
    for href in (
        "/mtas-admin/services/metabase",
        "/mtas-admin/services/openrefine",
        "/mtas-admin/auto-creation",
    ):
        assert f'href="{href}"' in menu
    text = admin_client.get("/mtas-admin/users").text
    assert "<summary>Services" in text


def test_old_settings_address_leads_to_the_settings_page(admin_client):
    response = admin_client.get("/mtas-admin/configs", follow_redirects=False)
    assert response.headers["location"] == "/mtas-admin/settings"


def test_visibility_is_grouped_by_category_and_service(admin_client, db):
    text = admin_client.get("/mtas-admin/visibility").text
    # stacked blocks over the full width, as on the services page of a user
    assert '<div class="block-list">' in text and "grid two" not in text
    services = text.index("<h2>Services</h2>")
    menu = text.index("<h2>Menu</h2>")
    assert services < menu

    def block(group):
        start = text.index(f'<th colspan="4">{group}</th>')
        return text[start : text.index("</table>", start)]

    postgresql = block("PostgreSQL")
    for key in (
        "postgresql",
        "importers_flights",
        "importers_airbnb",
        "importers_adventureworks",
    ):
        assert f"<code>{key}</code>" in postgresql
    assert "Dataset importer: Flights" in postgresql

    metabase = block("Metabase")
    assert "Service on the services page" in metabase
    assert "Users can start it" in metabase
    assert "metabase_self_managment" in metabase

    entries = block("Menu entries")
    assert text.index('<th colspan="4">Menu entries</th>') > menu
    assert "Reviews of the exercises" in entries and "Bonus points" in entries


def test_unknown_visibility_keys_are_in_other(db):
    from app.models import UIVisibilitySettings
    from app.visibility import (
        add_default_ui_visibility_settings,
        grouped_visibility_rows,
    )

    add_default_ui_visibility_settings(db)
    db.add(UIVisibilitySettings(ui_key="old_key", visible=True, description="Old part"))
    db.commit()
    groups = grouped_visibility_rows(db)
    assert list(groups) == ["Services", "Menu", "Other"]
    assert [label for _row, label in groups["Other"]["Other"]] == ["Old part"]
    assert list(groups["Services"])[:3] == ["PostgreSQL", "pgAdmin 4", "Metabase"]


def test_visibility_columns_line_up(admin_client):
    text = admin_client.get("/mtas-admin/visibility").text
    # every block has the same fixed columns: key, description, status, action
    columns = (
        '<colgroup><col class="col-key"><col><col class="col-status">'
        '<col class="col-action"></colgroup>'
    )
    assert text.count('<table class="table visibility-table">') == text.count(columns)
    assert "<th>Key</th>" not in text
    row = text[text.rindex("<tr>", 0, text.index("<code>bonus</code>")) :]
    row = row[: row.index("</tr>")]
    assert (
        row.index('class="col-key"')
        < row.index("Bonus points")
        < row.index('class="col-status"')
        < row.index('class="col-action"')
    )


def test_static_files_change_their_address_with_the_file(client, tmp_path, monkeypatch):
    from app import web

    (tmp_path / "css").mkdir()
    css = tmp_path / "css" / "app.css"
    css.write_text("a {}")
    monkeypatch.setattr(web, "STATIC_DIR", tmp_path)
    os.utime(css, (1000, 1000))
    assert web.static_url("css/app.css") == "/static/css/app.css?v=1000"
    os.utime(css, (2000, 2000))
    assert web.static_url("css/app.css") == "/static/css/app.css?v=2000"


def test_settings_values_are_marked(admin_client):
    text = admin_client.get("/mtas-admin/settings").text
    assert '<td class="setting-value">mtas.example.org</td>' in text
    # an empty value shows a dash
    assert (
        '<code>CONTAINER_NAME_PREFIX</code></td>\n            <td class="setting-value">–</td>'
        in text
    )
