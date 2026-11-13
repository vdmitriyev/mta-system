"""Client of the sqlmate API: creates the accounts of the users.

sqlmate creates a user with an e-mail address and answers with the PIN and a
personal login link. The API needs REGISTRATION_API=True in sqlmate and an API key
(SQLMATE_API_KEY, the same value as API_KEY in sqlmate).
"""

import logging
from dataclasses import dataclass

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)


class SqlmateError(Exception):
    """sqlmate did not answer or refused the request"""


@dataclass(frozen=True)
class SqlmateAccount:
    login: str
    pin: str
    login_url: str
    created: bool


def _request(method: str, path: str, **kwargs) -> requests.Response:
    settings = get_settings()
    if settings.sqlmate_api_key is None:
        raise SqlmateError("SQLMATE_API_KEY is not set")
    url = settings.sqlmate_api_url.rstrip("/") + path
    headers = {"Authorization": f"Bearer {settings.sqlmate_api_key.get_secret_value()}"}
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=settings.service_api_timeout_sec,
            **kwargs,
        )
    except requests.RequestException as error:
        raise SqlmateError(f"sqlmate is not reachable: {error}") from error
    if response.status_code >= 400:
        try:
            message = response.json().get("error", response.text)
        except ValueError:
            message = response.text[:200]
        raise SqlmateError(f"sqlmate answered {response.status_code}: {message}")
    return response


def _account(data: dict) -> SqlmateAccount:
    return SqlmateAccount(
        login=data["email"],
        pin=str(data["pin"]),
        login_url=data["login_url"],
        created=bool(data.get("created")),
    )


def ping() -> str:
    """Checks the address and the API key. Returns the name of the key."""

    return _request("GET", "/ping").json().get("key", "")


def create_user(email: str) -> SqlmateAccount:
    """Creates the user (or gets the existing one). sqlmate sends no e-mail."""

    response = _request("POST", "/users", json={"email": email, "notify": False})
    return _account(response.json())


def get_user(email: str) -> SqlmateAccount:
    return _account(_request("GET", f"/users/{email}").json())
