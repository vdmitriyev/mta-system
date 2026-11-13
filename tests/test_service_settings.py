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
from tests.conftest import force_on, post, switch_on


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
    set_creates_accounts(db, "metabase", True)
    assert creates_accounts(db, "metabase") is True
    set_creates_accounts(db, "metabase", False)
    assert creates_accounts(db, "metabase") is False


@pytest.mark.parametrize("service", ["nifi", "superset", "jupyterhub"])
def test_deprecated_services_cannot_be_switched_on(db, service):
    with pytest.raises(ServiceSettingError, match="is deprecated"):
        set_creates_accounts(db, service, True)
    # an old "on" in the database has no effect, switching off works
    force_on(db, service)
    assert creates_accounts(db, service) is False
    set_creates_accounts(db, service, False)


def test_auto_creation_page_shows_deprecated_services(admin_client, db):
    text = admin_client.get("/mtas-admin/auto-creation").text
    for name, key in (
        ("NiFi", "nifi"),
        ("Superset", "superset"),
        ("JupyterHub", "jupyterhub"),
    ):
        start = text.index(f"<strong>{name}</strong>")
        row = text[start : text.index("</tr>", start)]
        assert '<span class="badge warning">deprecated</span>' in row
        assert f'value="{key}"' not in row  # no button
    start = text.index("<strong>Metabase</strong>")
    assert "deprecated" not in text[start : text.index("</tr>", start)]


def test_visibility_marks_deprecated_services(admin_client):
    text = admin_client.get("/mtas-admin/visibility").text
    assert 'NiFi <span class="badge warning">deprecated</span>' in text
    assert 'Metabase <span class="badge warning">' not in text


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
    text = admin_client.get("/mtas-admin/auto-creation").text
    assert "<title>Auto creation" in text
    for service in SERVICE_KEYS:
        assert f"<code>{service}</code>" in text


def test_admin_switches_a_service_on(admin_client, db):
    response = post(
        admin_client,
        "/mtas-admin/auto-creation",
        {"service": "metabase", "on": "true"},
    )
    assert response.status_code == 303
    db.expire_all()
    assert creates_accounts(db, "metabase") is True
    text = admin_client.get("/mtas-admin/auto-creation").text
    assert "The app now creates an account in Metabase for new users." in text


def test_admin_sees_why_wordpress_cannot_be_switched_on(admin_client, db):
    post(
        admin_client,
        "/mtas-admin/auto-creation",
        {"service": "wordpress", "on": "true"},
    )
    text = admin_client.get("/mtas-admin/auto-creation").text
    assert "Switch on MariaDB first" in text
    db.expire_all()
    assert creates_accounts(db, "wordpress") is False


def test_students_cannot_change_the_switches(student_client, db):
    response = student_client.get("/mtas-admin/auto-creation")
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
        cli, ["auto-creation", "--on", "wordpress", "--on", "mariadb"]
    )
    assert result.exit_code == 0, result.output
    assert "wordpress    on" in result.output
    assert "metabase     off" in result.output

    result = runner.invoke(
        cli, ["auto-creation", "--off", "mariadb", "--off", "wordpress"]
    )
    assert result.exit_code == 0, result.output
    assert "mariadb      off" in result.output


def test_cli_names_the_problem(settings, db):
    init_engine(settings.database_url)
    result = CliRunner().invoke(cli, ["auto-creation", "--on", "wordpress"])
    assert result.exit_code == 1
    assert "Switch on MariaDB first" in result.output


def test_table_splits_name_and_how_it_runs(admin_client):
    text = admin_client.get("/mtas-admin/auto-creation").text
    for cells in (
        [
            "<strong>PostgreSQL</strong>",
            "One shared server, an own database for each user",
        ],
        [
            "<strong>pgAdmin 4</strong>",
            "One shared service, an own login for each user",
            "Needs PostgreSQL",
        ],
        ["<strong>Metabase</strong>", "An own container for each user"],
        [
            "<strong>WordPress</strong>",
            "An own container for each user",
            "Needs MariaDB",
        ],
    ):
        start = text.index(cells[0])
        row = text[start : text.index("</tr>", start)]
        for cell in cells[1:]:
            assert cell in row
    assert "<th>How it runs</th>" in text


def test_old_auto_creation_address(admin_client):
    response = admin_client.get("/mtas-admin/service-accounts", follow_redirects=False)
    assert response.headers["location"] == "/mtas-admin/auto-creation"


def test_every_service_has_a_name_and_a_way_to_run():
    from app.service_settings import SERVICES

    assert all(service.name and service.runs for service in SERVICES)


def test_versions_of_the_own_containers(admin_client, use_settings):
    use_settings(OPENREFINE_VERSION="3.9.5")
    text = admin_client.get("/mtas-admin/auto-creation").text
    for name, image, setting in (
        ("Metabase", "metabase/metabase:v0.57.3", "METABASE_VERSION"),
        ("OpenRefine", "openrefine:3.9.5", "OPENREFINE_VERSION"),
        ("WordPress", "wordpress:latest", "WORDPRESS_VERSION, WORDPRESS_CLI_VERSION"),
        ("MariaDB", "mariadb:13.0.2", "MARIADB_VERSION"),
    ):
        start = text.index(f"<strong>{name}</strong>")
        row = text[start : text.index("</tr>", start)]
        assert f"<code>{image}</code>" in row and "setting " not in row
    for name, image, setting in (
        ("PostgreSQL", "postgres:17.11", "POSTGRESQL_VERSION"),
        ("pgAdmin 4", "dpage/pgadmin4:9.19", "PGADMIN4_VERSION"),
    ):
        start = text.index(f"<strong>{name}</strong>")
        row = text[start : text.index("</tr>", start)]
        assert f"<code>{image}</code>" in row and "setting " not in row
    # services without a known version
    start = text.index("<strong>Superset</strong>")
    assert "<code>" not in text[start : text.index("<td><code>superset", start)]
    assert "<th>Version</th>" in text


def test_wordpress_shows_both_images(admin_client, use_settings):
    use_settings(WORDPRESS_VERSION="6.8", WORDPRESS_CLI_VERSION="cli-2.12")
    text = admin_client.get("/mtas-admin/auto-creation").text
    start = text.index("<strong>WordPress</strong>")
    row = text[start : text.index("</tr>", start)]
    assert "<code>wordpress:6.8</code><br><code>wordpress:cli-2.12</code>" in row


def test_note_names_the_versions_file(admin_client):
    text = admin_client.get("/mtas-admin/auto-creation").text
    note = text.index(
        '<p class="page-note">The versions come from the file <code>versions.env</code>'
    )
    assert note > text.index("</table>")
