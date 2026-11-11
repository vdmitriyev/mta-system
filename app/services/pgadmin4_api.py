from app.services import basic_auth


def new_user_pgadmin4_for_web_auth(user_name: str, user_password: str) -> bool:
    """Creates the login of a user for pgAdmin 4.

    nginx checks the login (basic auth) and passes the user name to pgAdmin 4.
    """

    return basic_auth.set_basic_auth_user(
        user_name, user_password, basic_auth.common_auth_file()
    )
