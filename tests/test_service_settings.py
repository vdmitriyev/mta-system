import pytest
from click.testing import CliRunner

from app.cli import cli
from app.database import init_engine, session_scope
from app.models import ServiceSettings
from app.service_settings import (
    SERVICE_KEYS,
    ServiceSettingError,
    add_default_service_settings,
    creates_accounts,
    service_setting_rows,
    set_creates_accounts,
)
from tests.conftest import post, switch_on


def test_all_services_are_off_by_default(db):
    add_default_service_settings(db)
    rows = service_setting_rows(db)
    assert [row.service for row in rows] == SERVICE_KEYS
    assert not any(row.create_accounts for row in rows)
    assert creates_accounts(db, "metabase") is False


def test_defaults_keep_the_changed_switches(db):
    switch_on(db, "metabase")
    add_default_service_settings(db)
    assert creates_accounts(db, "metabase") is True
    assert db.query(ServiceSettings).count() == len(SERVICE_KEYS)


def test_switch_on_and_off(db):
    set_creates_accounts(db, "nifi", True)
    assert creates_accounts(db, "nifi") is True
    set_creates_accounts(db, "nifi", False)
    assert creates_accounts(db, "nifi") is False


def test_unknown_service(db):
    with pytest.raises(ServiceSettingError, match="no service"):
        set_creates_accounts(db, "oracle", True)


def test_wordpress_needs_mariadb(db):
    with pytest.raises(ServiceSettingError, match="Switch on MariaDB first"):
        set_creates_accounts(db, "wordpress", True)
    switch_on(db, "mariadb", "wordpress")
    with pytest.raises(ServiceSettingError, match="Switch off WordPress first"):
        set_creates_accounts(db, "mariadb", False)
    assert creates_accounts(db, "mariadb") is True


def test_admin_page_lists_the_services(admin_client):
    text = admin_client.get("/mtas-admin/service-accounts").text
    assert "Service accounts" in text
    for service in SERVICE_KEYS:
        assert f"<code>{service}</code>" in text


def test_admin_switches_a_service_on(admin_client, db):
    response = post(
        admin_client,
        "/mtas-admin/service-accounts",
        {"service": "metabase", "on": "true"},
    )
    assert response.status_code == 303
    db.expire_all()
    assert creates_accounts(db, "metabase") is True
    text = admin_client.get("/mtas-admin/service-accounts").text
    assert "creates an account in “metabase”" in text


def test_admin_sees_why_wordpress_cannot_be_switched_on(admin_client, db):
    post(
        admin_client,
        "/mtas-admin/service-accounts",
        {"service": "wordpress", "on": "true"},
    )
    text = admin_client.get("/mtas-admin/service-accounts").text
    assert "Switch on MariaDB first" in text
    db.expire_all()
    assert creates_accounts(db, "wordpress") is False


def test_students_cannot_change_the_switches(student_client, db):
    response = student_client.get("/mtas-admin/service-accounts")
    assert response.status_code in (403, 404)


def test_migration_copies_the_old_env_switches(settings, tmp_path, monkeypatch):
    env_file = tmp_path / "old.env"
    env_file.write_text("CREATE_NIFI_SERVICE=true\nCREATE_METABASE_SERVICE=true\n")
    monkeypatch.setenv("ENV_FILE_NAME", str(env_file))
    # the environment wins over the env file
    monkeypatch.setenv("CREATE_METABASE_SERVICE", "false")
    monkeypatch.setenv("CREATE_POSTGRESQL_SERVICE", "TRUE")

    init_engine(settings.database_url)
    result = CliRunner().invoke(cli, ["db-upgrade"])
    assert result.exit_code == 0, result.output

    with session_scope() as db:
        on = {row.service for row in service_setting_rows(db) if row.create_accounts}
        assert on == {"nifi", "postgresql"}
        assert len(service_setting_rows(db)) == len(SERVICE_KEYS)


def test_cli_shows_and_changes_the_switches(settings, db):
    init_engine(settings.database_url)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["service-accounts", "--on", "wordpress", "--on", "mariadb"]
    )
    assert result.exit_code == 0, result.output
    assert "wordpress    on" in result.output
    assert "metabase     off" in result.output

    result = runner.invoke(
        cli, ["service-accounts", "--off", "mariadb", "--off", "wordpress"]
    )
    assert result.exit_code == 0, result.output
    assert "mariadb      off" in result.output


def test_cli_names_the_problem(settings, db):
    init_engine(settings.database_url)
    result = CliRunner().invoke(cli, ["service-accounts", "--on", "wordpress"])
    assert result.exit_code == 1
    assert "Switch on MariaDB first" in result.output
