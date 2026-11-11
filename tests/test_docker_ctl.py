import pytest

from app.services import docker_ctl


def test_statuses_of_known_and_unknown_containers(docker):
    docker.containers.add("metabase-3001", "running")
    docker.containers.add("openrefine-4001", "exited")

    statuses = docker_ctl.container_statuses(
        ["metabase-3001", "openrefine-4001", "nifi-6001", None]
    )
    assert statuses == {
        "metabase-3001": "running",
        "openrefine-4001": "exited",
        "nifi-6001": "unknown",
    }
    assert docker_ctl.container_statuses([]) == {}


def test_start_and_stop(docker):
    container = docker.containers.add("metabase-3001", "exited")
    assert docker_ctl.run_action("metabase-3001", "start") is True
    assert container.status == "running"
    assert docker_ctl.run_action("metabase-3001", "stop") is True
    assert container.status == "exited"


def test_action_on_a_missing_container_fails(docker):
    assert docker_ctl.run_action("metabase-9999", "start") is False
    assert docker_ctl.run_action(None, "start") is False


def test_unknown_action_is_an_error(docker):
    with pytest.raises(ValueError):
        docker_ctl.run_action("metabase-3001", "remove")


def test_retire_container(docker):
    container = docker.containers.add("metabase-3001", "running")
    assert docker_ctl.retire_container("metabase-3001", "metabase-3001-old") is True
    assert (container.name, container.status) == ("metabase-3001-old", "exited")
    assert docker_ctl.retire_container("metabase-3001", "x") is False


def test_retire_container_reports_an_error(docker):
    container = docker.containers.add("metabase-3001")

    def broken(_name):
        raise RuntimeError("conflict")

    container.rename = broken
    assert docker_ctl.retire_container("metabase-3001", "x") is False


def test_containers_info_and_summary(docker):
    docker.containers.add("metabase-3001", "running", logs=b"started\n")
    broken = docker.containers.add("nifi-6001", "exited")

    def no_logs(tail=20):
        raise RuntimeError("gone")

    broken.logs = no_logs
    broken.image = None

    info = docker_ctl.containers_info()
    assert info[0] == {
        "id": "id-metabase-",
        "name": "metabase-3001",
        "image": "metabase:latest",
        "status": "running",
        "logs": "started\n",
    }
    assert "Cannot read the logs" in info[1]["logs"]
    assert info[1]["image"] == "unknown"
    assert docker_ctl.containers_summary() == {"total": 2, "running": 1, "exited": 1}


def test_everything_works_without_docker(no_docker):
    assert docker_ctl.list_containers() == []
    assert docker_ctl.container_statuses(["a"]) == {"a": "unknown"}
    assert docker_ctl.run_action("a", "start") is False
    assert docker_ctl.retire_container("a", "b") is False
    assert docker_ctl.containers_info() == []
    assert docker_ctl.containers_summary() == {"total": 0, "running": 0, "exited": 0}


def test_list_failure_gives_an_empty_list(docker):
    def broken(all=False):
        raise RuntimeError("daemon error")

    docker.containers.list = broken
    assert docker_ctl.list_containers() == []


def test_get_client_uses_the_docker_package(monkeypatch):
    import docker as docker_package

    monkeypatch.setattr(docker_package, "from_env", lambda: "client")
    assert docker_ctl.get_client() == "client"


def test_check_image_on_the_server(docker):
    check = docker_ctl.check_image("metabase/metabase:v0.57.3", hint="x", command="y")
    assert check.ok
    assert (check.state, check.image) == (
        "Image is on this server",
        "metabase/metabase:v0.57.3",
    )
    # nothing to do: no hint and no command
    assert (check.hint, check.command) == ("", "")


def test_check_image_in_the_registry(docker):
    docker.images.missing.add("metabase/metabase:v0.57.3")
    docker.images.in_registry.add("metabase/metabase:v0.57.3")
    check = docker_ctl.check_image("metabase/metabase:v0.57.3")
    assert check.ok and "Docker downloads it" in check.state

    check = docker_ctl.check_image("metabase/metabase:v0.57.3", ask_registry=False)
    assert not check.ok


def test_check_image_missing_everywhere(docker):
    docker.images.missing.add("openrefine:3.9.5")
    check = docker_ctl.check_image(
        "openrefine:3.9.5", hint="Build it on the server:", command="docker build ."
    )
    assert not check.ok
    assert check.text == (
        "Image is not on this server and not in the registry: openrefine:3.9.5. "
        "Build it on the server: docker build ."
    )


def test_check_image_without_docker(no_docker):
    check = docker_ctl.check_image("openrefine:3.9.5")
    assert not check.ok and "No access to Docker" in check.text
