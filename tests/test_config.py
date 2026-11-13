import os

import pytest

from app import config
from app.config import ConfigError, Settings, get_settings, load_settings, set_settings
from tests.conftest import BASE_ENV


def test_defaults_for_development():
    settings = Settings.from_env(BASE_ENV)
    assert settings.debug is True
    assert settings.production is False
    assert settings.enable_api_docs is True
    assert settings.session_cookie_secure is False
    assert settings.services_ui == config.DEFAULT_SERVICES_UI
    assert settings.database_url.endswith("data/mta-system.db")


def test_defaults_for_production():
    settings = Settings.from_env({**BASE_ENV, "TARGET_SERVER": "production"})
    assert settings.debug is False
    assert settings.production is True
    assert settings.enable_api_docs is False
    assert settings.session_cookie_secure is True


def test_api_docs_can_be_switched_on_in_production():
    env = {**BASE_ENV, "TARGET_SERVER": "production", "ENABLE_API_DOCS": "true"}
    assert Settings.from_env(env).enable_api_docs is True


def test_api_docs_can_be_switched_off_in_development():
    assert (
        Settings.from_env({**BASE_ENV, "ENABLE_API_DOCS": "false"}).enable_api_docs
        is False
    )


def test_unknown_target_server_is_an_error():
    with pytest.raises(ConfigError, match="TARGET_SERVER"):
        Settings.from_env({**BASE_ENV, "TARGET_SERVER": "staging"})


@pytest.mark.parametrize("key", ["SECRET_KEY", "HASH_KEY_HIDDEN", "HASH_KEY_LINKS"])
def test_missing_secret_is_an_error(key):
    env = {k: v for k, v in BASE_ENV.items() if k != key}
    with pytest.raises(ConfigError, match=key):
        Settings.from_env(env)


def test_old_name_of_the_secret_key_still_works():
    env = {k: v for k, v in BASE_ENV.items() if k != "SECRET_KEY"}
    env["FLASK_SECRET_KEY"] = "old-secret"
    assert Settings.from_env(env).secret_key.get_secret_value() == "old-secret"


def test_lists_are_split_at_semicolons():
    env = {**BASE_ENV, "SYSTEM_ADMINS": "a@x.org; b@x.org;", "SERVICES_UI": "metabase"}
    settings = Settings.from_env(env)
    assert settings.system_admins == ["a@x.org", "b@x.org"]
    assert settings.services_ui == ["metabase"]


@pytest.mark.parametrize(
    "value",
    [
        "uol.de;uni-oldenburg.de",
        "uol.de, uni-oldenburg.de",
        "['uol.de', 'uni-oldenburg.de']",
        '["UOL.de", "@uni-oldenburg.de"]',
        " uol.de ; uni-oldenburg.de ; ",
    ],
)
def test_allowed_email_domains_formats(value):
    settings = Settings.from_env({**BASE_ENV, "ALLOWED_FQDN_FOR_EMAILS": value})
    assert settings.allowed_fqdn_for_emails == ["uol.de", "uni-oldenburg.de"]


def test_system_admins_are_lower_case():
    settings = Settings.from_env({**BASE_ENV, "SYSTEM_ADMINS": "Ada@Uni.example"})
    assert settings.system_admins == ["ada@uni.example"]


@pytest.mark.parametrize("value", ["", "[]"])
def test_no_allowed_domains_allows_all(value):
    settings = Settings.from_env({**BASE_ENV, "ALLOWED_FQDN_FOR_EMAILS": value})
    assert settings.allowed_fqdn_for_emails == []


@pytest.mark.parametrize(
    "value,expected", [("TRUE", True), ("1", True), ("no", False), ("", False)]
)
def test_flags(value, expected):
    env = {**BASE_ENV, "SESSION_COOKIE_SECURE": value}
    assert Settings.from_env(env).session_cookie_secure is expected


def test_old_service_switches_in_the_env_file_are_ignored():
    env = {**BASE_ENV, "CREATE_METABASE_SERVICE": "true"}
    assert not hasattr(Settings.from_env(env), "create_metabase_service")


def test_absolute_database_path_is_kept(tmp_path):
    settings = Settings.from_env({**BASE_ENV, "MTAS_DB_PATH": str(tmp_path / "x.db")})
    assert settings.database_url == f"sqlite:///{tmp_path / 'x.db'}"


def test_urls_use_the_server_name():
    settings = Settings.from_env(BASE_ENV)
    assert settings.base_url == "https://mtas.example.org/"
    assert settings.pgadmin4_url == "https://mtas.example.org/pgadmin4"
    assert (
        settings.container_url("metabase", 3001)
        == "https://mtas.example.org/metabase/3001/"
    )
    assert settings.jupyterhub_url.endswith("/jupyterhub/")
    assert settings.superset_url == "https://mtas.example.org:8089/"
    assert settings.wordpress_base_url == "http://mtas.example.org/wordpress/"


def test_public_items_hide_secrets():
    items = Settings.from_env({**BASE_ENV, "MAIL_PASSWORD": "mail-pw"}).public_items()
    assert items["SERVER_FQDN"] == "mtas.example.org"
    text = str(items)
    for secret in ("test-secret-key", "test-hash-key", "mail-pw", "sqlite://"):
        assert secret not in text


def test_get_settings_reads_the_environment_once(monkeypatch):
    set_settings(None)
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("COURSE_NAME_TITLE", "From Env")
    try:
        assert get_settings().course_name_title == "From Env"
        monkeypatch.setenv("COURSE_NAME_TITLE", "Changed")
        assert get_settings().course_name_title == "From Env"
    finally:
        set_settings(None)


def test_secrets_are_hidden_in_the_repr():
    settings = Settings.from_env({**BASE_ENV, "POSTGRESQL_ADMIN_PASSWORD": "pg-pw"})
    assert "pg-pw" not in repr(settings)
    assert settings.postgresql_admin_password.get_secret_value() == "pg-pw"
    assert settings.hash_key_links.get_secret_value() == b"test-hash-key-links"


@pytest.mark.parametrize(
    "key,value",
    [
        ("MAIL_PORT", "abc"),
        ("MAIL_PORT", "70000"),
        ("SESSION_MAX_AGE_DAYS", "0"),
        ("ENABLE_API_DOCS", "maybe"),
    ],
)
def test_wrong_values_name_the_variable(key, value):
    with pytest.raises(ConfigError, match=key):
        Settings.from_env({**BASE_ENV, key: value})


def test_empty_values_use_the_default():
    settings = Settings.from_env({**BASE_ENV, "MAIL_PORT": "", "SERVER_FQDN": " "})
    assert settings.mail_port == 587
    assert settings.server_fqdn == "localhost"


def test_absolute_basic_auth_dir_wins(tmp_path):
    env = {
        **BASE_ENV,
        "NGINX_BASIC_AUTH_DIR": "relative",
        "NGINX_BASIC_AUTH_DIR_ABSOLUTE": str(tmp_path),
    }
    assert Settings.from_env(env).nginx_basic_auth_dir == str(tmp_path)
    env = {**BASE_ENV, "NGINX_BASIC_AUTH_DIR": "relative"}
    assert Settings.from_env(env).nginx_basic_auth_dir == str(
        config.BASE_DIR / "relative"
    )


@pytest.fixture
def clean_env(monkeypatch):
    """No settings in the environment of the test process"""

    for key in list(os.environ):
        if key.lower() in Settings.model_fields or key in (
            "FLASK_SECRET_KEY",
            "NGINX_BASIC_AUTH_DIR_ABSOLUTE",
            "ENV_FILE_NAME",
        ):
            monkeypatch.delenv(key)
    return monkeypatch


def write_env_file(path, **values):
    lines = [f"{key}={value}" for key, value in {**BASE_ENV, **values}.items()]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_load_settings_reads_the_env_file(tmp_path, clean_env):
    env_file = write_env_file(tmp_path / "app.env", COURSE_NAME_TITLE="'From File'")
    clean_env.setenv("ENV_FILE_NAME", str(env_file))
    assert load_settings().course_name_title == "From File"


def test_environment_wins_over_the_env_file(tmp_path, clean_env):
    env_file = write_env_file(tmp_path / "app.env", COURSE_NAME_TITLE="From File")
    clean_env.setenv("ENV_FILE_NAME", str(env_file))
    clean_env.setenv("COURSE_NAME_TITLE", "From Shell")
    assert load_settings().course_name_title == "From Shell"


def test_load_settings_warns_about_a_missing_env_file(tmp_path, clean_env, caplog):
    clean_env.setenv("ENV_FILE_NAME", str(tmp_path / "missing.env"))
    for key, value in BASE_ENV.items():
        clean_env.setenv(key, value)
    load_settings()
    assert "does not exist" in caplog.text


def test_load_settings_uses_the_default_env_file(tmp_path, clean_env):
    (tmp_path / "envs").mkdir()
    write_env_file(tmp_path / config.DEFAULT_ENV_FILE, COURSE_NAME_TITLE="Default")
    clean_env.setattr(config, "BASE_DIR", tmp_path)
    assert load_settings().course_name_title == "Default"


def test_load_settings_names_the_missing_secret(tmp_path, clean_env):
    clean_env.setenv("ENV_FILE_NAME", str(tmp_path / "missing.env"))
    with pytest.raises(ConfigError, match="Set the environment variable SECRET_KEY"):
        load_settings()


def test_image_versions(tmp_path):
    settings = Settings.from_env(BASE_ENV)
    assert (
        settings.metabase_version,
        settings.openrefine_version,
        settings.wordpress_version,
    ) == ("v0.57.3", "3.10.1", "latest")


@pytest.mark.parametrize("value", ["3.10 .1", "latest;rm -rf /", ":3.10", "-x"])
def test_wrong_image_version_names_the_variable(value):
    with pytest.raises(ConfigError, match="OPENREFINE_VERSION"):
        Settings.from_env({**BASE_ENV, "OPENREFINE_VERSION": value})


def test_versions_come_from_the_central_file():
    versions = config.read_versions()
    assert set(versions) == {
        "METABASE_VERSION",
        "OPENREFINE_VERSION",
        "WORDPRESS_VERSION",
        "POSTGRESQL_VERSION",
        "PGADMIN4_VERSION",
        "MARIADB_VERSION",
        "WORDPRESS_CLI_VERSION",
        "SQLMATE_VERSION",
        "SQLMATE_SOURCE",
        "SURVEYLITE_VERSION",
        "SURVEYLITE_SOURCE",
    }
    settings = Settings.from_env(BASE_ENV)
    assert settings.openrefine_version == versions["OPENREFINE_VERSION"]
    assert settings.metabase_version == versions["METABASE_VERSION"]
    assert settings.postgresql_version == versions["POSTGRESQL_VERSION"]
    assert settings.pgadmin4_version == versions["PGADMIN4_VERSION"]
    assert settings.mariadb_version == versions["MARIADB_VERSION"]
    assert settings.wordpress_cli_version == versions["WORDPRESS_CLI_VERSION"]
    assert settings.sqlmate_version == versions["SQLMATE_VERSION"]
    assert settings.surveylite_version == versions["SURVEYLITE_VERSION"]


def test_env_file_and_environment_win_over_the_versions_file(tmp_path, clean_env):
    env_file = write_env_file(tmp_path / "app.env", OPENREFINE_VERSION="3.9.5")
    clean_env.setenv("ENV_FILE_NAME", str(env_file))
    settings = load_settings()
    assert settings.openrefine_version == "3.9.5"
    assert settings.metabase_version == config.read_versions()["METABASE_VERSION"]

    clean_env.setenv("METABASE_VERSION", "v0.56.0")
    assert load_settings().metabase_version == "v0.56.0"


def test_missing_versions_file_is_named(tmp_path, clean_env, caplog):
    env_file = write_env_file(tmp_path / "app.env")
    clean_env.setenv("ENV_FILE_NAME", str(env_file))
    clean_env.setattr(config, "VERSIONS_FILE", tmp_path / "missing-versions.env")
    with pytest.raises(
        ConfigError, match="Set the environment variable METABASE_VERSION"
    ):
        load_settings()
    assert "Versions file does not exist" in caplog.text


@pytest.mark.parametrize("value", ["Upper-", "-dash", "with space-", "a/b-"])
def test_wrong_container_prefix(value):
    with pytest.raises(ConfigError, match="CONTAINER_NAME_PREFIX"):
        Settings.from_env({**BASE_ENV, "CONTAINER_NAME_PREFIX": value})
