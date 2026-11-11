from sqlalchemy import insert, inspect
from sqlalchemy.orm import Session

from app.models import UIVisibilitySettings

# Default UI visibility settings: (ui_key, visible, description)
DEFAULT_UI_VISIBILITY_SETTINGS = [
    ("pgadmin4", True, "pgAdmin 4 service"),
    ("postgresql", True, "PostgreSQL service"),
    ("importers_flights", True, "Dataset importer: flights"),
    ("importers_airbnb", True, "Dataset importer: Airbnb"),
    ("importers_adventureworks", True, "Dataset importer: AdventureWorks"),
    ("metabase", True, "Metabase service"),
    ("metabase_self_managment", True, "Metabase: users can start it"),
    ("openrefine", True, "OpenRefine service"),
    ("openrefine_self_managment", True, "OpenRefine: users can start it"),
    ("mariadb", True, "MariaDB service"),
    ("mariadb_self_managment", True, "MariaDB: users can start it"),
    ("wordpress", True, "WordPress service"),
    ("wordpress_self_managment", True, "WordPress: users can start it"),
    ("nifi", True, "NiFi service"),
    ("nifi_self_managment", True, "NiFi: users can start it"),
    ("superset", True, "Superset service"),
    ("jupyterhub", True, "JupyterHub service"),
    ("reviews", True, "Menu: reviews of the exercises"),
    ("bonus", True, "Menu: bonus points"),
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
