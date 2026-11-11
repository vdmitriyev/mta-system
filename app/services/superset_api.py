import logging

import requests
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)


class SupersetUser:
    def __init__(self, login: str, password: str, email: str):
        self.login = login
        self.password = password
        self.email = email


class SupersetAPIClient:
    """Creates users in Superset through its web forms (as the admin)"""

    def __init__(self, new_user: SupersetUser):
        settings = get_settings()
        self.new_user = new_user
        self.base_url = settings.superset_base_url
        self.session = None
        self.csrf_token = None
        password = settings.superset_password
        self.start_session(
            settings.superset_login, password.get_secret_value() if password else None
        )

    def start_session(self, admin_login: str, admin_password: str) -> None:
        """Logs in as the admin and keeps the CSRF token"""

        session = requests.Session()
        response = session.get(self.base_url + "/login/", timeout=60)
        token_field = BeautifulSoup(response.content, "html.parser").find(
            "input", id="csrf_token"
        )
        if token_field is None:
            logger.error("Superset login page has no CSRF token")
            return

        csrf_token = token_field["value"]
        try:
            session.post(
                self.base_url + "/login/",
                data={
                    "username": admin_login,
                    "password": admin_password,
                    "csrf_token": csrf_token,
                },
                timeout=60,
            )
        except requests.RequestException as error:
            logger.error("Superset login failed: %s", error)
            return

        self.session = session
        self.csrf_token = csrf_token

    def user_exists(self) -> bool:
        response = self.session.get(
            f"{self.base_url}/users/api/read",
            headers={"X-CSRFToken": self.csrf_token},
            timeout=60,
        )
        for user in response.json()["result"]:
            if (
                user["email"] == self.new_user.email
                or user["username"] == self.new_user.login
            ):
                return True
        return False

    def user_create(self) -> bool:
        tokens = self.new_user.email.split("@")[0].split(".")
        if len(tokens) < 2:
            tokens = ["Unknown", "Unknown"]

        payload = {
            "first_name": tokens[0].capitalize(),
            "last_name": tokens[1].capitalize(),
            "username": self.new_user.login,
            "email": self.new_user.email,
            "password": self.new_user.password,
            "conf_password": self.new_user.password,
            "active": "y",
            "roles": [3, 4, 7],  # the maximum privileges, after admin
        }
        response = self.session.post(
            f"{self.base_url}/users/api/create",
            data=payload,
            headers={"X-CSRFToken": self.csrf_token},
            timeout=60,
        )
        if response.status_code >= 400:
            logger.error("Superset user was not created: %s", response.status_code)
            return False
        return True

    def create_new_user(self) -> bool:
        """Creates the user. Returns True if the user exists afterwards."""

        if self.session is None:
            return False
        if self.user_exists():
            logger.info("Superset user already exists: %s", self.new_user.login)
            return True
        return self.user_create()
