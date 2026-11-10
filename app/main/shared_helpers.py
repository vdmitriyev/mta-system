from sqlalchemy import insert, inspect

from ..extensions import db
from ..models import UIVisibilitySettings

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


def add_default_ui_visibility_settings() -> None:
    """Adds the default UI visibility settings that are not in the database yet.
    Settings that already exist are not changed.
    """

    if not inspect(db.engine).has_table(UIVisibilitySettings.__tablename__):
        return

    rows = [
        {"ui_key": ui_key, "visible": visible, "description": description}
        for ui_key, visible, description in DEFAULT_UI_VISIBILITY_SETTINGS
    ]
    # "OR IGNORE" (SQLite) skips existing keys, also when several workers start at once
    db.session.execute(insert(UIVisibilitySettings).prefix_with("OR IGNORE"), rows)
    db.session.commit()


def ui_visibility_settings() -> dict:
    """Gets UI visibility settings from the database

    Returns:
        dict: dictionary that contains UI visibility settings
    """

    ui_visibility = {}
    ui_visibility_fb = (
        db.session.query(UIVisibilitySettings)
        .order_by(UIVisibilitySettings.ui_key)
        .all()
    )

    for _element in ui_visibility_fb:
        ui_visibility[_element.ui_key] = _element.visible

    return ui_visibility


def change_ui_visibility_settings(ui_key: str, visibility: bool) -> None:
    """Changes the visibility of the UI element

    Args:
        ui_key (str): key of the UI element
        visibility (bool): new value of the UI visibility setting
    """

    db.session.query(UIVisibilitySettings).filter(
        UIVisibilitySettings.ui_key == ui_key
    ).update({"visible": visibility})
    db.session.commit()
