from dataclasses import dataclass

from sqlalchemy import insert, inspect
from sqlalchemy.orm import Session

from app.models import UIVisibilitySettings

SERVICES_CATEGORY = "Services"
MENU_CATEGORY = "Menu"
OTHER = "Other"


@dataclass(frozen=True)
class VisibilityItem:
    """A part of the UI that the admin can show or hide (all are shown at the start)"""

    ui_key: str
    category: str
    group: str
    label: str


SERVICE_CARD = "Service on the services page"
SELF_START = "Users can start it"

VISIBILITY_ITEMS = [
    VisibilityItem("postgresql", SERVICES_CATEGORY, "PostgreSQL", SERVICE_CARD),
    VisibilityItem(
        "importers_flights",
        SERVICES_CATEGORY,
        "PostgreSQL",
        "Dataset importer: Flights",
    ),
    VisibilityItem(
        "importers_airbnb", SERVICES_CATEGORY, "PostgreSQL", "Dataset importer: Airbnb"
    ),
    VisibilityItem(
        "importers_adventureworks",
        SERVICES_CATEGORY,
        "PostgreSQL",
        "Dataset importer: AdventureWorks",
    ),
    VisibilityItem("pgadmin4", SERVICES_CATEGORY, "pgAdmin 4", SERVICE_CARD),
    VisibilityItem("metabase", SERVICES_CATEGORY, "Metabase", SERVICE_CARD),
    VisibilityItem(
        "metabase_self_managment", SERVICES_CATEGORY, "Metabase", SELF_START
    ),
    VisibilityItem("openrefine", SERVICES_CATEGORY, "OpenRefine", SERVICE_CARD),
    VisibilityItem(
        "openrefine_self_managment", SERVICES_CATEGORY, "OpenRefine", SELF_START
    ),
    VisibilityItem("mariadb", SERVICES_CATEGORY, "MariaDB", SERVICE_CARD),
    VisibilityItem("mariadb_self_managment", SERVICES_CATEGORY, "MariaDB", SELF_START),
    VisibilityItem("wordpress", SERVICES_CATEGORY, "WordPress", SERVICE_CARD),
    VisibilityItem(
        "wordpress_self_managment", SERVICES_CATEGORY, "WordPress", SELF_START
    ),
    VisibilityItem("nifi", SERVICES_CATEGORY, "NiFi", SERVICE_CARD),
    VisibilityItem("nifi_self_managment", SERVICES_CATEGORY, "NiFi", SELF_START),
    VisibilityItem("superset", SERVICES_CATEGORY, "Superset", SERVICE_CARD),
    VisibilityItem("jupyterhub", SERVICES_CATEGORY, "JupyterHub", SERVICE_CARD),
    VisibilityItem(
        "reviews", MENU_CATEGORY, "Menu entries", "Reviews of the exercises"
    ),
    VisibilityItem("bonus", MENU_CATEGORY, "Menu entries", "Bonus points"),
]
VISIBILITY_INFO = {item.ui_key: item for item in VISIBILITY_ITEMS}

# (ui_key, visible, description) for the database
DEFAULT_UI_VISIBILITY_SETTINGS = [
    (item.ui_key, True, f"{item.group}: {item.label}") for item in VISIBILITY_ITEMS
]


def add_default_ui_visibility_settings(db: Session) -> None:
    """Adds the default UI visibility settings that are not in the database yet.
    Settings that already exist are not changed.
    """

    if not inspect(db.get_bind()).has_table(UIVisibilitySettings.__tablename__):
        return

    rows = [
        {"ui_key": ui_key, "visible": visible, "description": description}
        for ui_key, visible, description in DEFAULT_UI_VISIBILITY_SETTINGS
    ]
    # "OR IGNORE" (SQLite) skips existing keys, also when several workers start at once
    db.execute(insert(UIVisibilitySettings).prefix_with("OR IGNORE"), rows)
    db.commit()


def ui_visibility_settings(db: Session) -> dict:
    """Gets the UI visibility settings: ui_key -> visible"""

    rows = db.query(UIVisibilitySettings).order_by(UIVisibilitySettings.ui_key).all()
    return {row.ui_key: row.visible for row in rows}


def ui_visibility_rows(db: Session) -> list:
    return db.query(UIVisibilitySettings).order_by(UIVisibilitySettings.ui_key).all()


def change_ui_visibility_settings(db: Session, ui_key: str, visible: bool) -> bool:
    """Changes the visibility of a UI element. Returns False if there is no such element."""

    changed = (
        db.query(UIVisibilitySettings)
        .filter(UIVisibilitySettings.ui_key == ui_key)
        .update({"visible": visible})
    )
    db.commit()
    return changed > 0


def grouped_visibility_rows(db: Session) -> dict:
    """Rows grouped for the admin page: category -> group -> [(row, label)].

    Categories and groups are in the order of VISIBILITY_ITEMS. Unknown keys are in "Other".
    """

    order = {item.ui_key: number for number, item in enumerate(VISIBILITY_ITEMS)}
    rows = sorted(
        ui_visibility_rows(db), key=lambda row: order.get(row.ui_key, len(order))
    )
    groups = {}
    for row in rows:
        item = VISIBILITY_INFO.get(row.ui_key)
        category = item.category if item else OTHER
        group = item.group if item else OTHER
        label = item.label if item else (row.description or row.ui_key)
        groups.setdefault(category, {}).setdefault(group, []).append((row, label))
    return groups
