"""Client of the surveylite API: anonymous participants, surveys and personal links.

surveylite never learns who a participant is: the app creates the participant
without a label and keeps the link to the user in its own table (SurveyliteService).
The API key is SURVEYLITE_API_KEY (one of SURVEYLITE_API_KEYS in surveylite).
"""

import logging
from dataclasses import dataclass

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

COMPLETED = "completed"


class SurveyliteError(Exception):
    """surveylite did not answer or refused the request"""


@dataclass(frozen=True)
class Participant:
    id: str
    login: str
    pin: str
    dashboard_url: str
    # personal login link: opens /me without the login and the PIN (secret as the PIN)
    login_url: str | None = None


@dataclass(frozen=True)
class Survey:
    id: int
    title: str
    status: str
    slug: str = ""
    # only the logged-in participant can answer (survey link alone is not enough)
    require_login: bool = False


@dataclass(frozen=True)
class SurveyLink:
    survey_id: int
    url: str
    status: str
    participant_id: str | None = None
    # survey link that also logs the participant in (secret as the PIN)
    auth_url: str | None = None


def _request(method: str, path: str, **kwargs) -> requests.Response:
    settings = get_settings()
    if settings.surveylite_api_key is None:
        raise SurveyliteError("SURVEYLITE_API_KEY is not set")
    url = settings.surveylite_api_url.rstrip("/") + path
    headers = {"X-API-Key": settings.surveylite_api_key.get_secret_value()}
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=settings.service_api_timeout_sec,
            **kwargs,
        )
    except requests.RequestException as error:
        raise SurveyliteError(f"surveylite is not reachable: {error}") from error
    if response.status_code >= 400:
        try:
            message = response.json().get("detail", response.text)
        except ValueError:
            message = response.text[:200]
        raise SurveyliteError(f"surveylite answered {response.status_code}: {message}")
    return response


def _link(data: dict) -> SurveyLink:
    return SurveyLink(
        survey_id=int(data["survey_id"]),
        url=data["url"],
        status=data["status"],
        participant_id=data.get("participant_id"),
        auth_url=data.get("auth_url"),
    )


def list_surveys() -> list[Survey]:
    return [
        Survey(
            id=int(item["id"]),
            title=item["title"],
            status=item["status"],
            slug=item.get("slug", ""),
            require_login=bool(item.get("require_login", False)),
        )
        for item in _request("GET", "/surveys").json()
    ]


def create_participant() -> Participant:
    """Creates an anonymous participant: no label, nothing that points to the user"""

    data = _request("POST", "/participants").json()
    return Participant(
        id=data["id"],
        login=data["login"],
        pin=str(data["pin"]),
        dashboard_url=data["dashboard_url"],
        login_url=data.get("login_url"),
    )


def login_link(participant_id: str, renew: bool = False) -> str:
    """The personal login link of a participant. renew: a new link, the old one stops working"""

    method = "POST" if renew else "GET"
    return _request(method, f"/participants/{participant_id}/login-link").json()[
        "login_url"
    ]


def assign(survey_id: int, participant_ids: list[str]) -> list[SurveyLink]:
    """Gives the participants a personal link to the survey (safe to repeat)"""

    response = _request(
        "POST",
        f"/surveys/{survey_id}/assignments",
        json={"participant_ids": participant_ids},
    )
    return [_link(item) for item in response.json()]


def participant_links(participant_id: str) -> list[SurveyLink]:
    """The surveys of a participant with their status"""

    return [
        _link(item)
        for item in _request("GET", f"/participants/{participant_id}/links").json()
    ]
