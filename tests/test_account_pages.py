import pytest

from app.models import (
    BackgroundTask,
    ExerciseBonusPoints,
    ExerciseReviews,
    JupyterHubService,
    MariaDBService,
    MetabaseService,
    NiFiService,
    OpenRefineService,
    PGAdmin4Service,
    SupersetService,
    WordpressService,
)
from app.visibility import change_ui_visibility_settings
from tests.conftest import add_exercise, add_postgresql, add_user, post


def add_all_services(db, user):
    add_postgresql(db, user)
    uid = user.itid
    db.add_all(
        [
            PGAdmin4Service(
                user_id=uid,
                pgadmin4_user="common_user_01",
                pgadmin4_password="pga-secret",
            ),
            MetabaseService(
                user_id=uid,
                metabase_login="x",
                metabase_password="mb-secret",
                metabase_docker_port=3001,
            ),
            OpenRefineService(
                user_id=uid,
                openrefine_user="common_user_01",
                openrefine_password="or-secret",
                openrefine_docker_port=4001,
            ),
            NiFiService(
                user_id=uid,
                nifi_user="nifi_user_01",
                nifi_password="nifi-secret",
                nifi_docker_port=6001,
            ),
            MariaDBService(
                user_id=uid,
                mariadb_db="mariadb_wordpress_db_7001",
                mariadb_user="mariadb_user_01",
                mariadb_password="maria-secret",
            ),
            WordpressService(
                user_id=uid,
                wordpress_login="wordpress_user_01",
                wordpress_password="wp-secret",
                wordpress_docker_port=7001,
            ),
            SupersetService(
                user_id=uid,
                superset_user="bicourse_user_01",
                superset_password="ss-secret",
            ),
            JupyterHubService(
                user_id=uid,
                jupyterhub_user="jh_user_01",
                jupyterhub_password="jh-secret",
            ),
        ]
    )
    db.commit()


def test_services_page_without_services(student_client, no_docker):
    response = student_client.get("/services")
    assert response.status_code == 200
    assert "No services are set up" in response.text


def test_services_page_shows_all_services_of_the_user(
    student_client, db, student, docker
):
    add_all_services(db, student)
    docker.containers.add("metabase-3001", "running")
    docker.containers.add("openrefine-4001", "exited")

    text = student_client.get("/services").text
    for title in [
        "PostgreSQL",
        "pgAdmin 4",
        "Metabase",
        "OpenRefine",
        "Apache NiFi",
        "MariaDB",
        "WordPress",
        "Apache Superset",
        "JupyterHub",
    ]:
        assert f"<h2>{title}" in text or title in text, title
    assert "https://mtas.example.org/metabase/3001/" in text
    assert "https://mtas.example.org/nifi/6001/nifi/" in text
    assert "https://mtas.example.org/wordpress/7001/wp-admin/" in text
    assert "https://mtas.example.org/pgadmin4" in text
    assert "jdbc:postgresql://mtas.example.org:5432/bicourse_db_01" in text
    assert "bicourse_db_01" in text
    assert 'data-container-status="metabase">running' in text
    assert 'data-container-status="openrefine">exited' in text
    assert 'data-container-status="nifi">unknown' in text
    assert text.count('action="/services/') == 4
    # values that nobody needs to copy have no copy button
    assert 'data-copy="5432"' not in text
    assert 'data-copy="bicourse_db_01"' in text


def test_services_follow_the_order_of_the_settings(
    student_client, db, student, no_docker
):
    add_all_services(db, student)
    text = student_client.get("/services").text
    positions = [
        text.index(f'id="service-{name}"')
        for name in ("pgadmin4", "postgresql", "metabase", "jupyterhub")
    ]
    assert positions == sorted(positions)


def test_passwords_are_masked_until_the_user_shows_them(
    student_client, db, student, no_docker
):
    add_all_services(db, student)
    text = student_client.get("/services").text
    assert 'data-secret="pg-secret-11">••••••••<' in text
    assert ">pg-secret-11<" not in text


def test_hidden_services_and_importers_are_not_shown(
    student_client, db, student, no_docker
):
    add_all_services(db, student)
    change_ui_visibility_settings(db, "metabase", False)
    change_ui_visibility_settings(db, "openrefine_self_managment", False)
    change_ui_visibility_settings(db, "importers_airbnb", False)

    text = student_client.get("/services").text
    assert 'id="service-metabase"' not in text
    assert 'id="service-openrefine"' in text
    assert 'action="/services/openrefine/start"' not in text
    assert 'value="flights"' in text
    assert 'value="airbnb"' not in text


def test_user_sees_only_own_services(student_client, db, student, no_docker):
    other = add_user(db, email="other@uni.example", number=9)
    add_postgresql(db, other, number=9)
    assert "bicourse_db_09" not in student_client.get("/services").text


def test_start_own_container(student_client, db, student, docker):
    add_all_services(db, student)
    container = docker.containers.add("metabase-3001", "exited")

    response = post(student_client, "/services/metabase/start")
    assert response.headers["location"] == "/services"
    assert container.status == "running"
    assert "The service starts" in student_client.get("/services").text


def test_start_fails_without_container(student_client, db, student, docker):
    add_all_services(db, student)
    post(student_client, "/services/metabase/start")
    assert "was not started" in student_client.get("/services").text


@pytest.mark.parametrize("service", ["postgresql", "unknown", "nifi"])
def test_start_of_other_services_is_404(student_client, db, student, docker, service):
    add_postgresql(db, student)
    assert post(student_client, f"/services/{service}/start").status_code == 404


def test_start_is_404_if_the_admin_switched_it_off(student_client, db, student, docker):
    add_all_services(db, student)
    change_ui_visibility_settings(db, "metabase_self_managment", False)
    assert post(student_client, "/services/metabase/start").status_code == 404


def test_start_needs_login_and_csrf_token(client, student_client):
    assert student_client.post("/services/metabase/start").status_code == 403


def test_dataset_import_runs_in_the_background(
    student_client, db, student, no_docker, monkeypatch
):
    add_postgresql(db, student)
    seen = []
    monkeypatch.setattr(
        "app.routers.account.import_dataset_task",
        lambda _db, user_id, dataset: seen.append((user_id, dataset))
        or "Flights was imported",
    )

    response = post(student_client, "/importer", {"dataset": "flights"})
    assert response.headers["location"] == "/services"
    assert seen == [(student.itid, "flights")]

    task = db.query(BackgroundTask).one()
    assert (task.kind, task.user_id, task.status) == (
        "import:flights",
        student.itid,
        "done",
    )
    text = student_client.get("/services").text
    assert "Last imports" in text and "Flights was imported" in text


def test_running_import_is_shown_and_not_started_twice(
    student_client, db, student, no_docker
):
    add_postgresql(db, student)
    db.add(
        BackgroundTask(
            public_id="c" * 32,
            kind="import:flights",
            user_id=student.itid,
            status="running",
        )
    )
    db.commit()

    text = student_client.get("/services").text
    assert "Importing Flights" in text
    assert f'data-task="{"c" * 32}"' in text

    post(student_client, "/importer", {"dataset": "flights"})
    assert db.query(BackgroundTask).count() == 1


@pytest.mark.parametrize("dataset", ["unknown", ""])
def test_import_of_an_unknown_dataset(student_client, db, student, no_docker, dataset):
    add_postgresql(db, student)
    post(student_client, "/importer", {"dataset": dataset})
    assert db.query(BackgroundTask).count() == 0
    assert "no such dataset" in student_client.get("/services").text


def test_import_of_a_hidden_dataset(student_client, db, student, no_docker):
    add_postgresql(db, student)
    change_ui_visibility_settings(db, "importers_flights", False)
    post(student_client, "/importer", {"dataset": "flights"})
    assert db.query(BackgroundTask).count() == 0


def test_import_without_database(student_client, db, no_docker):
    post(student_client, "/importer", {"dataset": "flights"})
    assert db.query(BackgroundTask).count() == 0
    assert "no PostgreSQL database" in student_client.get("/services").text


def test_reviews_page(student_client, db, student):
    shown = add_exercise(db, "EX1", "Data model")
    hidden_review = add_exercise(db, "EX2", "ETL process", order=2)
    add_exercise(db, "EX3", "Not open", order=3)
    add_exercise(db, "EX4", "Invisible exercise", order=4, visible=False)
    db.add(
        ExerciseReviews(
            user_id=student.itid,
            exercise_id=shown.itid,
            content="**Well done**",
            submitted=True,
            reviewed=True,
            visible=True,
        )
    )
    db.add(
        ExerciseReviews(
            user_id=student.itid,
            exercise_id=hidden_review.itid,
            content="draft text",
            submitted=True,
            reviewed=False,
            visible=False,
        )
    )
    db.commit()

    text = student_client.get("/reviews").text
    assert "<strong>Well done</strong>" in text
    assert "draft text" not in text
    assert "under review" in text
    assert "not submitted" in text
    assert "Invisible exercise" not in text


def test_reviews_page_without_exercises(student_client):
    assert "no exercises with reviews" in student_client.get("/reviews").text


def test_bonus_page(student_client, db, student):
    first = add_exercise(db, "EX1", "Data model")
    second = add_exercise(db, "EX2", "ETL process", order=2)
    add_exercise(db, "EX3", "No bonus", order=3, has_bonus=False)
    db.add(
        ExerciseBonusPoints(user_id=student.itid, exercise_id=first.itid, points=4.5)
    )
    db.add(
        ExerciseBonusPoints(
            user_id=student.itid, exercise_id=second.itid, points=2.0, visible=False
        )
    )
    db.commit()

    text = student_client.get("/bonus").text
    assert "Data model" in text and "ETL process" in text
    assert "No bonus" not in text
    assert ">4.5<" in text.replace(" ", "").replace("\n", "")
    assert "6.5" in text


def test_bonus_page_without_exercises(student_client):
    assert "no exercises with bonus points" in student_client.get("/bonus").text


def test_menu_entries_can_be_hidden(student_client, db):
    change_ui_visibility_settings(db, "reviews", False)
    change_ui_visibility_settings(db, "bonus", False)
    text = student_client.get("/").text
    assert 'href="/reviews"' not in text
    assert 'href="/bonus"' not in text
