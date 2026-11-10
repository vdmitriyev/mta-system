import argparse
import json
import os
import re
import warnings
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.services.common import (
    create_user_basic_auth_common,
    get_nginx_basic_auth_directory,
    print_msg,
)


def new_user_pgadmin4_for_web_auth(
    user_name: str, user_password: str, logger=None
) -> bool:
    """Create a user in the pgadmin4 to be used via basic authentication

    Args:
        user_name (str): user's name
        user_password (str): user's password
        logger (_type_, optional): logger to be used. Defaults to None.

    Returns:
        bool: True if user was created successfully
    """

    NGINX_BASIC_AUTH_FILE_EXTENSION = (
        os.getenv("NGINX_BASIC_AUTH_FILE_EXTENSION") or ".htpasswd"
    )
    NGINX_BASIC_AUTH_COMMON_DB = (
        os.environ.get("NGINX_BASIC_AUTH_COMMON_DB") or "common-basic-auth.db"
    )

    nginx_basic_auth_dir = get_nginx_basic_auth_directory()
    auth_file = os.path.join(nginx_basic_auth_dir, NGINX_BASIC_AUTH_FILE_EXTENSION)

    auth_file = os.path.join(nginx_basic_auth_dir, NGINX_BASIC_AUTH_COMMON_DB)

    return create_user_basic_auth_common(user_name, user_password, auth_file)


def new_user_pgadmin4(
    user_email: str,
    user_password: str,
    admin_email: str = None,
    admin_password: str = None,
    logger=None,
) -> bool:
    """Create a user in the pgadmin4 using direct HTTP requests as a usual web form would do

    Args:
        user_email (str): user's email
        user_password (str): user's password
        admin_email (str, optional): admin's email for auth
        admin_password (str, optional): admin's password for auth
        logger (_type_, optional): logger to be used. Defaults to None.

    Returns:
        bool: True if user was created successfully
    """

    warnings.warn("This function is deprecated.", category=DeprecationWarning)

    PGADMIN4_BASE_URL = os.environ.get("PGADMIN4_BASE_URL")
    PGADMIN_EMAIL = os.environ.get("PGADMIN_EMAIL")
    PGADMIN_PASSWORD = os.environ.get("PGADMIN_PASSWORD")

    print_msg('Run method "new_user_pgadmin4"', logger)

    is_created = False
    if admin_email is None:
        admin_email = PGADMIN_EMAIL
    if admin_password is None:
        admin_password = PGADMIN_PASSWORD

    print_msg("PGAdmin4 endpoint: {0}".format(PGADMIN4_BASE_URL), logger)

    with requests.Session() as sess:

        url_base = PGADMIN4_BASE_URL
        res = sess.get(url_base + "/login")
        csrf_token = __get_csrf_token(res)

        print_msg("The csrf_token found: {0}".format(csrf_token), logger)

        payload_auth = {
            "email": "{0}".format(admin_email),
            "password": "{0}".format(admin_password),
        }
        payload_auth["csrf_token"] = csrf_token

        try:
            res = sess.post(url_base + "/login", data=payload_auth, timeout=60)
            print_msg(
                "Status of getting csrf_token: {0}".format(res.status_code), logger
            )
        except Exception as ex:
            print_msg("[e] Exception (POST): {0}".format(ex), logger)
        print(sess.cookies)

        # create new user
        url_new_user = "{baseURL}/user_management/save".format(baseURL=url_base)
        payload_new_user = {}

        payload_new_user = (
            '{"added":[{'
            + '"auth_source":"internal","email":"{0}","role":"2","active":true,"newPassword":"{1}","confirmPassword":"{1}","locked":false'
            "".format(user_email, user_password) + "}]}"
        )

        headers = {}
        headers["X-Pga-Csrftoken"] = csrf_token
        headers["Referer"] = res.url
        headers["Content-Type"] = "application/json"

        res_new_user = sess.post(url_new_user, data=payload_new_user, headers=headers)

        if res_new_user.status_code == 200:
            is_created = True
            print_msg('User in "pgadmin4" backend was created successfully.', logger)
        print(res_new_user.text)

        if res_new_user.status_code != 200:

            print_msg(
                "Status of creating new user [200 expected]: {0}".format(
                    res_new_user.status_code
                ),
                logger,
            )

            # handle situation with password change
            if "UNIQUE constraint failed" in res_new_user.text:
                # get all users
                url_users = "{baseURL}/user_management/user/".format(baseURL=url_base)
                res_users = sess.get(url_users, headers=headers)
                json_content = json.loads(res_users.text)
                found_user = None
                for value in json_content:
                    if value["email"] == user_email:
                        found_user = value
                        break

                if found_user is not None:
                    user_id = found_user["id"]
                    payload_new_password = '"id":{id},"newPassword":"{password}","confirmPassword":"{password}"'.format(
                        id=user_id, password=user_password
                    )
                    payload_new_password = (
                        '{"changed":[{' + payload_new_password + "}]}"
                    )

                    headers = {}
                    headers["X-pgA-CSRFToken"] = csrf_token
                    headers["Referer"] = res.url
                    res_new_password = sess.put(
                        url_new_user + str(user_id),
                        data=payload_new_password,
                        headers=headers,
                    )
                    print_msg(
                        "New password operation response code: {0}. Text: {1}".format(
                            res_new_password.status_code, res_new_password.text
                        ),
                        logger,
                    )
                    is_created = True
                else:
                    print_msg(
                        'Password is not changed, the user "{0}"was not found.'.format(
                            user_email
                        ),
                        logger,
                    )
                    is_created = False
            else:
                print_msg("Do not know how to handle following error.", logger)
                print_msg("Response body: \n {0}".format(res_new_user._content), logger)
                is_created = False

    return is_created


def __get_csrf_token(req) -> str:
    """_summary_

    Args:
        req (_type_): request object

    Returns:
        str: token found in the text
    """

    csrf_token = None
    signin_html = BeautifulSoup(req._content, "html.parser")
    script_tags = signin_html.find_all("script")
    for script_tag in script_tags:
        csrf_token_match = re.search(r'"csrfToken": "(.*?)"', script_tag.text)
        if csrf_token_match:
            csrf_token = csrf_token_match.group(1)
            break

    if csrf_token is None:
        print_msg("csrf_token not found in the JavaScript code.")

    return csrf_token


def main(user_name, user_password):
    print("[i] Create pgadmin4 user using the script approach")
    new_user_pgadmin4_for_web_auth(user_name, user_password)


if __name__ == "__main__":

    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--username", required=True, help="userName")
    ap.add_argument("-p", "--password", required=True, help="userPasword")

    args = vars(ap.parse_args())

    main(user_email=args["username"], user_password=args["password"])
