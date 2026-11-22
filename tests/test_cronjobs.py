"""Cron jobs: nightly stop of the users' containers (app/cronjobs.py, command stop-containers)"""

import pytest
from click.testing import CliRunner

from app.cli import cli
from app.cronjobs import STOP_TIMEOUT, stop_user_containers
from app.models import (
    AdminActions,
    MetabaseService,
    OpenRefineService,
    WordpressService,
)
from app.services import docker_ctl
from tests.conftest import add_user


def add_containers(db, user, number, deleted=False):
    db.add_all(
        [
            MetabaseService(
                user_id=user.itid,
                metabase_login="x",
                metabase_password="pw",
                metabase_docker_port=3000 + number,
                deleted=deleted,
            ),
            OpenRefineService(
                user_id=user.itid,
                openrefine_user=f"common_user_{number:02}",
                openrefine_password="pw",
                openrefine_docker_port=4000 + number,
                deleted=deleted,
            ),
            WordpressService(
                user_id=user.itid,
                wordpress_login="wp",
                wordpress_password="pw",
                wordpress_docker_port=7000 + number,
            ),
        ]
    )
    db.commit()


@pytest.fixture
def users(db, docker):
    first = add_user(db, email="first@uni.example", number=1)
    second = add_user(db, email="second@uni.example", number=2)
    add_containers(db, first, 1)
    add_containers(db, second, 2)
    for name in ("metabase-3001", "openrefine-4001", "wordpress-7001", "metabase-3002"):
        docker.containers.add(name, "running")
    docker.containers.add("openrefine-4002", "exited")
    return first, second


def statuses(docker) -> dict:
    return {c.name: c.status for c in docker.containers.list(all=True)}


def test_running_containers_are_stopped_and_noted(db, docker, users):
    first, second = users
    stopped = stop_user_containers(db, ["metabase", "openrefine"])

    assert sorted(c.name for c in stopped) == [
        "metabase-3001",
        "metabase-3002",
        "openrefine-4001",
    ]
    assert statuses(docker) == {
        "metabase-3001": "exited",
        "openrefine-4001": "exited",
        "wordpress-7001": "running",  # not in the list of services
        "metabase-3002": "exited",
        "openrefine-4002": "exited",  # was already stopped
    }
    assert docker.containers.get("metabase-3001").stop_timeout == STOP_TIMEOUT

    entries = db.query(AdminActions).order_by(AdminActions.itid).all()
    assert [(e.action, e.admin_id, e.user_id, e.details) for e in entries] == [
        ("service_stop_night", None, first.itid, "Metabase: metabase-3001"),
        ("service_stop_night", None, second.itid, "Metabase: metabase-3002"),
        ("service_stop_night", None, first.itid, "OpenRefine: openrefine-4001"),
    ]


def test_containers_of_deleted_accounts_are_left_alone(db, docker):
    user = add_user(db, number=5)
    add_containers(db, user, 5, deleted=True)
    old = docker.containers.add("metabase-3005", "running")
    assert stop_user_containers(db, ["metabase"]) == []
    assert old.status == "running"


def test_only_the_given_services(db, docker, users):
    stopped = stop_user_containers(db, ["metabase"])
    assert {c.service for c in stopped} == {"metabase"}
    assert docker.containers.get("openrefine-4001").status == "running"
    assert stop_user_containers(db, []) == []


def test_a_service_without_containers_is_skipped(db, docker, users):
    assert stop_user_containers(db, ["postgresql"]) == []


def test_admin_log_page_shows_the_nightly_stop(admin_client, db, docker, users):
    stop_user_containers(db, ["metabase"])
    text = admin_client.get("/mtas-admin/actions").text
    assert "Container stopped (night)" in text
    assert "Metabase: metabase-3001" in text


def test_run_action_passes_the_stop_timeout(docker):
    container = docker.containers.add("metabase-3009", "running")
    assert docker_ctl.run_action("metabase-3009", "stop", timeout=60) is True
    assert (container.status, container.stop_timeout) == ("exited", 60)


@pytest.fixture
def runner(settings):
    return CliRunner()


def test_command_stops_the_services_of_the_setting(
    runner, use_settings, db, docker, users
):
    use_settings(NIGHT_STOP_SERVICES="openrefine")
    result = runner.invoke(cli, ["stop-containers"])
    assert result.exit_code == 0, result.output
    assert "[i] stopped openrefine-4001" in result.output
    assert "[i] stopped containers: 1 (openrefine)" in result.output
    assert docker.containers.get("metabase-3001").status == "running"


def test_command_dry_run_stops_nothing(runner, db, docker, users):
    result = runner.invoke(cli, ["stop-containers", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "[i] would stop metabase-3001" in result.output
    assert "[i] running containers: 3" in result.output
    assert set(statuses(docker).values()) == {"running", "exited"}
    assert docker.containers.get("metabase-3001").status == "running"
    assert db.query(AdminActions).count() == 0


def test_command_with_one_service(runner, db, docker, users):
    result = runner.invoke(cli, ["stop-containers", "--service", "metabase"])
    assert "[i] stopped containers: 2 (metabase)" in result.output
    assert docker.containers.get("openrefine-4001").status == "running"


def test_default_services_of_the_setting(settings):
    assert settings.night_stop_services == ["metabase", "openrefine"]
