"""Settings of the app.

Sources, highest priority first:

1. environment variables
2. the env file in ENV_FILE_NAME (default: envs/webapp-dev-local.env)
3. versions.env: the versions of the service images, shared with compose and Task
4. the defaults below

Empty values count as "not set". Wrong values stop the start with a clear message.
"""

import logging
import os
import re
from pathlib import Path
from typing import Annotated, Literal, Mapping, get_args

from dotenv import dotenv_values
from pydantic import (
    AliasChoices,
    Field,
    NonNegativeInt,
    PositiveInt,
    SecretBytes,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = os.path.join("envs", "webapp-dev-local.env")
# Versions of the service images. Also read by Taskfile.yaml and compose.services.yml.
VERSIONS_FILE = BASE_DIR / "versions.env"
SERVER_MODES = ("development", "production")
# Names of the accounts and databases that the app creates for the users
POSTGRESQL_DB_PREFIX = "bicourse_db"
POSTGRESQL_USER_PREFIX = "bicourse_user"
PGADMIN4_USER_PREFIX = "common_user"
OPENREFINE_USER_PREFIX = "common_user"
NIFI_USER_PREFIX = "nifi_user"
MARIADB_USER_PREFIX = "mariadb_user"
MARIADB_DB_PREFIX = "mariadb_wordpress_db"
WORDPRESS_USER_PREFIX = "wordpress_user"
JUPYTERHUB_USER_PREFIX = "jh_user"

# Port of a user's container = offset + number of the user
METABASE_PORT_OFFSET = 3000
OPENREFINE_PORT_OFFSET = 4000
NIFI_PORT_OFFSET = 6000
WORDPRESS_PORT_OFFSET = 7000

MAX_USERS_NGINX_GENERATE = 100

DEFAULT_SERVICES_UI = [
    "pgadmin4",
    "postgresql",
    "metabase",
    "openrefine",
    "mariadb",
    "wordpress",
    "nifi",
    "superset",
    "jupyterhub",
]

logger = logging.getLogger(__name__)

# Version of a Docker image ("tag"), e.g. v0.57.3 or 3.10.1
ImageVersion = Annotated[str, Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")]

# Lists in env files are separated by ";": "a@x.org; b@x.org"
SemicolonList = Annotated[list[str], NoDecode]
Port = Annotated[int, Field(ge=1, le=65535)]


class ConfigError(Exception):
    """A required setting is missing or wrong"""


class Settings(BaseSettings):
    """All settings of the app. The environment variable of a field is its name in upper case."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
    )

    # ---- mode ----
    target_server: Literal["development", "production"] = "development"
    # None: on in development, off in production
    enable_api_docs: bool | None = Field(None, validate_default=True)

    # ---- secrets ----
    secret_key: SecretStr = Field(
        validation_alias=AliasChoices("secret_key", "flask_secret_key")
    )
    hash_key_hidden: SecretBytes
    hash_key_links: SecretBytes
    # None: on in production, off in development
    session_cookie_secure: bool | None = Field(None, validate_default=True)
    session_max_age_days: PositiveInt = 30

    # ---- course ----
    course_security_code: str = "CODE"
    course_name_title: str | None = None
    server_fqdn: str = "localhost"
    system_admins: SemicolonList = []
    allowed_fqdn_for_emails: SemicolonList = []
    services_ui: SemicolonList = Field(
        default_factory=lambda: list(DEFAULT_SERVICES_UI)
    )
    max_user_accounts_to_create: PositiveInt = 5

    # ---- database of the app (relative paths start at the project folder) ----
    mtas_db_path: Path = Path("data", "mta-system.db")

    # ---- e-mail ----
    mail_server: str = "localhost"
    mail_port: Port = 587
    mail_username: str | None = None
    mail_password: SecretStr | None = None
    mail_default_sender: str | None = None
    mail_timeout_sec: PositiveInt = 10

    # ---- PostgreSQL service ----
    postgresql_db_host: str = "localhost"
    postgresql_db_host_port: Port = 5432
    postgresql_db_name: str = "postgres"
    postgresql_admin_user: str = "postgres"
    postgresql_admin_password: SecretStr = SecretStr("postgres")
    postgresql_demo_db: str = "db_demo"
    postgresql_demo_user: str = "db_user_demo"
    postgresql_demo_password: SecretStr = SecretStr("postgres")
    postgresql_demo_user_readonly: str = "db_user_demo_ro"
    postgresql_demo_user_readonly_password: SecretStr = SecretStr("postgres")

    # ---- MariaDB service ----
    mariadb_db_host: str = "localhost"
    mariadb_db_host_port: Port = 3306
    mariadb_admin_user: str = "mariadb"
    mariadb_admin_password: SecretStr = SecretStr("mariadb")

    # ---- nginx basic auth (NGINX_BASIC_AUTH_DIR_ABSOLUTE wins over NGINX_BASIC_AUTH_DIR) ----
    nginx_basic_auth_dir: str = Field(
        ".htpasswd_nginx",
        validation_alias=AliasChoices(
            "nginx_basic_auth_dir_absolute", "nginx_basic_auth_dir"
        ),
    )
    nginx_basic_auth_common_db: str = "common-basic-auth.db"
    nginx_basic_auth_file_extension: str = ".htpasswd"

    # ---- containers of the users ----
    docker_network_name: str = "mtas-network"
    # versions of the images that the app starts for each user
    # no defaults here: they are in versions.env
    metabase_version: ImageVersion
    openrefine_version: ImageVersion
    wordpress_version: ImageVersion
    wordpress_cli_version: ImageVersion
    # versions of the shared services (compose.services.yml)
    postgresql_version: ImageVersion
    pgadmin4_version: ImageVersion
    mariadb_version: ImageVersion
    metabase_base_url: str = "http://localhost"
    metabase_try_count: PositiveInt = 3
    metabase_try_sleep_sec: NonNegativeInt = 30
    superset_base_url: str | None = None
    superset_login: str | None = None
    superset_password: SecretStr | None = None

    @field_validator("target_server", mode="before")
    @classmethod
    def _lower_case(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("enable_api_docs")
    @classmethod
    def _api_docs_default(cls, value: bool | None, info: ValidationInfo) -> bool:
        if value is None:
            return info.data.get("target_server") != "production"
        return value

    @field_validator("session_cookie_secure")
    @classmethod
    def _cookie_default(cls, value: bool | None, info: ValidationInfo) -> bool:
        if value is None:
            return info.data.get("target_server") == "production"
        return value

    @field_validator(
        "system_admins", "allowed_fqdn_for_emails", "services_ui", mode="before"
    )
    @classmethod
    def _split_list(cls, value):
        """Accepts "a;b", "a, b" and "['a', 'b']" """

        if isinstance(value, str):
            value = value.strip().removeprefix("[").removesuffix("]")
            value = re.split(r"[;,]", value)
        if isinstance(value, (list, tuple)):
            return [
                str(item).strip(" \t'\"") for item in value if str(item).strip(" \t'\"")
            ]
        return value

    @field_validator("system_admins")
    @classmethod
    def _lower_case_emails(cls, value: list[str]) -> list[str]:
        return [email.lower() for email in value]

    @field_validator("allowed_fqdn_for_emails")
    @classmethod
    def _clean_domains(cls, value: list[str]) -> list[str]:
        return [domain.lower().lstrip("@") for domain in value]

    @field_validator("mtas_db_path")
    @classmethod
    def _db_path_in_project(cls, value: Path) -> Path:
        return value if value.is_absolute() else BASE_DIR / value

    @field_validator("nginx_basic_auth_dir")
    @classmethod
    def _auth_dir_in_project(cls, value: str) -> str:
        return os.path.join(BASE_DIR, value)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        """Settings from these values and versions.env only: no environment, no env file.

        For tests.
        """

        values = {
            key.lower(): value
            for key, value in {**read_versions(), **env}.items()
            if not (isinstance(value, str) and value.strip() == "")
        }
        try:
            return cls.model_validate(values)
        except ValidationError as error:
            raise _config_error(error) from None

    @property
    def production(self) -> bool:
        return self.target_server == "production"

    @property
    def debug(self) -> bool:
        return not self.production

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.mtas_db_path}"

    @property
    def base_url(self) -> str:
        return f"https://{self.server_fqdn}/"

    @property
    def pgadmin4_url(self) -> str:
        return f"https://{self.server_fqdn}/pgadmin4"

    @property
    def jupyterhub_url(self) -> str:
        return f"https://{self.server_fqdn}/jupyterhub/"

    @property
    def superset_url(self) -> str:
        return f"https://{self.server_fqdn}:8089/"

    @property
    def wordpress_base_url(self) -> str:
        return f"http://{self.server_fqdn}/wordpress/"

    def container_url(self, service: str, port: int) -> str:
        """URL of a user's container behind nginx, e.g. https://<server>/metabase/3001/"""

        return f"https://{self.server_fqdn}/{service}/{port}/"

    def public_items(self) -> dict:
        """Settings without secrets, for the admin UI"""

        return {
            name.upper(): getattr(self, name)
            for name, field in type(self).model_fields.items()
            if not _is_secret(field.annotation)
        }


def _is_secret(annotation) -> bool:
    secret_types = (SecretStr, SecretBytes)
    return annotation in secret_types or any(
        arg in secret_types for arg in get_args(annotation)
    )


def _config_error(error: ValidationError) -> ConfigError:
    """Turns the errors of pydantic into one message with the names of the variables"""

    messages = []
    for item in error.errors():
        name = str(item["loc"][0]).upper() if item["loc"] else ""
        if item["type"] == "missing":
            messages.append(f"Set the environment variable {name}")
        elif name:
            messages.append(f"{name}: {item['msg']}")
        else:
            messages.append(item["msg"].removeprefix("Value error, "))
    return ConfigError("; ".join(messages))


def env_file() -> Path:
    """The env file in ENV_FILE_NAME, else the default env file"""

    name = os.environ.get("ENV_FILE_NAME")
    return Path(name) if name else BASE_DIR / DEFAULT_ENV_FILE


def read_versions() -> dict:
    """The values in versions.env (empty if the file is missing)"""

    if not VERSIONS_FILE.is_file():
        return {}
    return {
        key: value
        for key, value in dotenv_values(VERSIONS_FILE).items()
        if value is not None
    }


def load_settings() -> Settings:
    """Reads the settings from the environment, the env file and versions.env"""

    path = env_file()
    if os.environ.get("ENV_FILE_NAME") and not path.is_file():
        logger.warning("Env file does not exist: %s", path)
    if not VERSIONS_FILE.is_file():
        logger.warning("Versions file does not exist: %s", VERSIONS_FILE)
    # later files win: the env file of the app wins over versions.env
    files = tuple(file for file in (VERSIONS_FILE, path) if file.is_file())
    try:
        return Settings(_env_file=files or None)
    except ValidationError as error:
        raise _config_error(error) from None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(settings: Settings | None) -> None:
    global _settings
    _settings = settings
