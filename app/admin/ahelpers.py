from flask import current_app
from flask_login import current_user
from markupsafe import Markup
from sqlalchemy import and_

from .. import settings as settings
from ..extensions import db
from ..main.mhelpers import email_to_name, get_user_data_simplified
from ..models import Users
from ..utils.uhelpers import to_json_sqla


def has_admin_rights() -> bool:
    """Checks if a user has an admin role

    Returns:
        bool: admin role or not
    """

    is_admin = False
    user_data = get_user_data_simplified(current_user.get_id())
    if "email" in user_data:
        for admin_email in current_app.config["SYSTEM_ADMINS"]:
            if admin_email == user_data["email"]:
                is_admin = True
                break

    return is_admin


def get_users_data(source_code: str) -> list:
    """Gets user data from database and adds additional information (email, accessURL).

    Args:
        source_code (str): Code of course to be used

    Returns:
        list: A list with user data
    """
    users = []
    users_lst = (
        db.session.query(Users)
        .filter(and_(Users.deleted == False, Users.course_code == source_code))
        .order_by(Users.email.asc())
        .all()
    )

    for index, user in enumerate(users_lst):
        user_json = to_json_sqla(user)
        user_json["name"] = email_to_name(user_json["email"])
        user_json["accessWithAuthURL"] = Markup(
            "{0}{1}?uHash={2}&pHash={3}".format(
                settings.BASE_URL, "login", user_json["url_hash"], user_json["pin_hash"]
            )
        )
        users.append(user_json)

    return users


def get_users_data_unformatted(source_code: str) -> list:
    """Gets user data in unformatted fashion (direct from database).

    Args:
        source_code (str): Code of course to be used

    Returns:
        list: A list with user data
    """

    users_lst = (
        db.session.query(Users)
        .filter(and_(Users.deleted == False, Users.course_code == source_code))
        .order_by(Users.email.asc())
        .all()
    )
    return users_lst
