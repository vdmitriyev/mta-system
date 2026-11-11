"""Switches in the database: in which services the app creates an account for a new user"""

from sqlalchemy import insert, inspect
from sqlalchemy.orm import Session

from app.models import ServiceSettings

# (service, description). All are off until an admin switches them on.
SERVICES = [
    ("postgresql", "PostgreSQL: own database"),
    ("pgadmin4", "pgAdmin 4: login (needs PostgreSQL)"),
    ("metabase", "Metabase: own container"),
    ("openrefine", "OpenRefine: own container"),
    ("mariadb", "MariaDB: own database"),
    ("wordpress", "WordPress: own container (needs MariaDB)"),
    ("nifi", "NiFi: own container"),
    ("superset", "Superset: login"),
    ("jupyterhub", "JupyterHub: login (an admin creates the account in JupyterHub)"),
]
SERVICE_KEYS = [service for service, _description in SERVICES]


class ServiceSettingError(Exception):
    """The switch cannot be changed"""


def add_default_service_settings(db: Session) -> None:
    """Adds the services that are not in the database yet (switched off)"""

    if not inspect(db.get_bind()).has_table(ServiceSettings.__tablename__):
        return
    rows = [
        {"service": service, "create_accounts": False, "description": description}
        for service, description in SERVICES
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

    row = db.query(ServiceSettings).filter(ServiceSettings.service == service).first()
    return bool(row and row.create_accounts)


def set_creates_accounts(db: Session, service: str, on: bool) -> None:
    """Switches the account creation of a service on or off"""

    if service not in SERVICE_KEYS:
        raise ServiceSettingError(f"There is no service “{service}”.")
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
