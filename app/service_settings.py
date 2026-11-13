"""Switches in the database: in which services the app creates an account for a new user"""

from dataclasses import dataclass

from sqlalchemy import insert, inspect
from sqlalchemy.orm import Session

from app.models import ServiceSettings

SHARED_SERVER = "One shared server, an own database for each user"
SHARED_SERVICE = "One shared service, an own login for each user"
OWN_CONTAINER = "An own container for each user"


@dataclass(frozen=True)
class ServiceInfo:
    key: str
    name: str
    runs: str
    note: str = ""
    # no longer supported: the app creates no new accounts in it
    deprecated: bool = False


# All are off until an admin switches them on (admin page "Auto creation")
SERVICES = [
    ServiceInfo("postgresql", "PostgreSQL", SHARED_SERVER),
    ServiceInfo("pgadmin4", "pgAdmin 4", SHARED_SERVICE, "Needs PostgreSQL"),
    ServiceInfo("metabase", "Metabase", OWN_CONTAINER),
    ServiceInfo("openrefine", "OpenRefine", OWN_CONTAINER),
    ServiceInfo("mariadb", "MariaDB", SHARED_SERVER),
    ServiceInfo("wordpress", "WordPress", OWN_CONTAINER, "Needs MariaDB"),
    ServiceInfo("sqlmate", "sqlmate", SHARED_SERVICE, "SQL exercises"),
    ServiceInfo(
        "surveylite",
        "SurveyLite",
        SHARED_SERVICE,
        "Anonymous surveys: only this app knows who a participant is",
    ),
    ServiceInfo("nifi", "NiFi", OWN_CONTAINER, deprecated=True),
    ServiceInfo("superset", "Superset", SHARED_SERVICE, deprecated=True),
    ServiceInfo("jupyterhub", "JupyterHub", SHARED_SERVICE, deprecated=True),
]
SERVICE_KEYS = [service.key for service in SERVICES]
DEPRECATED_SERVICES = {service.key for service in SERVICES if service.deprecated}
SERVICE_INFO = {service.key: service for service in SERVICES}


class ServiceSettingError(Exception):
    """The switch cannot be changed"""


def add_default_service_settings(db: Session) -> None:
    """Adds the services that are not in the database yet (switched off)"""

    if not inspect(db.get_bind()).has_table(ServiceSettings.__tablename__):
        return
    rows = [
        {"service": info.key, "create_accounts": False, "description": info.name}
        for info in SERVICES
    ]
    # "OR IGNORE" (SQLite) keeps the existing rows, also when several workers start at once
    db.execute(insert(ServiceSettings).prefix_with("OR IGNORE"), rows)
    db.commit()


def service_setting_rows(db: Session) -> list:
    order = {service: number for number, service in enumerate(SERVICE_KEYS)}
    rows = db.query(ServiceSettings).all()
    return sorted(rows, key=lambda row: order.get(row.service, len(order)))


def creates_accounts(db: Session, service: str) -> bool:
    """True if the app creates an account in this service for each new user"""

    if service in DEPRECATED_SERVICES:
        return False
    row = db.query(ServiceSettings).filter(ServiceSettings.service == service).first()
    return bool(row and row.create_accounts)


def set_creates_accounts(db: Session, service: str, on: bool) -> None:
    """Switches the account creation of a service on or off"""

    if service not in SERVICE_KEYS:
        raise ServiceSettingError(f"There is no service “{service}”.")
    if on and service in DEPRECATED_SERVICES:
        raise ServiceSettingError(
            f"{SERVICE_INFO[service].name} is deprecated: "
            "the app no longer creates accounts in it."
        )
    if service == "wordpress" and on and not creates_accounts(db, "mariadb"):
        raise ServiceSettingError(
            "Switch on MariaDB first: WordPress stores its data in MariaDB."
        )
    if service == "mariadb" and not on and creates_accounts(db, "wordpress"):
        raise ServiceSettingError(
            "Switch off WordPress first: WordPress stores its data in MariaDB."
        )

    add_default_service_settings(db)
    db.query(ServiceSettings).filter(ServiceSettings.service == service).update(
        {"create_accounts": on}
    )
    db.commit()
