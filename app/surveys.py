"""Surveys of surveylite in this app.

* An admin gives a survey to users: each user gets a personal link (SurveyAssignment).
* A service can need a completed survey (ServiceRequirement): until the user completed
  it, the services page shows the survey instead of the login of the service.

surveylite only knows anonymous participants. The link between a user and a
participant is the table SurveyliteService of this app.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ServiceRequirement, SurveyAssignment, SurveyliteService
from app.services import surveylite_api
from app.services.surveylite_api import COMPLETED, SurveyliteError

logger = logging.getLogger(__name__)

STATUS_TEXT = {
    "not_started": "not started",
    "in_progress": "started",
    "paused": "paused",
    COMPLETED: "completed",
    "declined": "declined",
}


def participant_of(db: Session, user_id: int) -> SurveyliteService | None:
    """The anonymous participant of a user (only if surveylite created it)"""

    return (
        db.query(SurveyliteService)
        .filter(
            SurveyliteService.user_id == user_id,
            SurveyliteService.deleted.is_(False),
            SurveyliteService.created.is_(True),
        )
        .order_by(SurveyliteService.itid.desc())
        .first()
    )


def assignments_of(db: Session, user_id: int) -> list[SurveyAssignment]:
    return (
        db.query(SurveyAssignment)
        .filter(SurveyAssignment.user_id == user_id)
        .order_by(SurveyAssignment.survey_id)
        .all()
    )


def public_link(url: str | None) -> str | None:
    """The link of SurveyLite with its public address (SURVEYLITE_URL).

    SurveyLite builds its links from its own SURVEYLITE_BASE_URL. Without the
    prefix /surveylite there, https://<host>/me?auth=... opens the page /me of this
    app. The app keeps only the path in SurveyLite and the query of the link.
    """

    if not url:
        return url
    public = get_settings().surveylite_public_url
    prefix = urlsplit(public).path or "/"
    parts = urlsplit(url)
    path = parts.path
    path = path[len(prefix) :] if path.startswith(prefix) else path.lstrip("/")
    return public + path + (f"?{parts.query}" if parts.query else "")


def survey_link(row: SurveyAssignment) -> str | None:
    """The link for the user: the one that also logs in, else the plain survey link"""

    return public_link(row.survey_auth_url or row.survey_url)


def _store_link(db: Session, user_id: int, title: str, link) -> SurveyAssignment:
    row = (
        db.query(SurveyAssignment)
        .filter(
            SurveyAssignment.user_id == user_id,
            SurveyAssignment.survey_id == link.survey_id,
        )
        .first()
    )
    if row is None:
        row = SurveyAssignment(user_id=user_id, survey_id=link.survey_id)
        db.add(row)
    if title:
        row.survey_title = title
    _set_link(row, link)
    return row


def _set_link(row: SurveyAssignment, link) -> None:
    row.survey_url = link.url
    if link.auth_url:
        row.survey_auth_url = link.auth_url
    _set_status(row, link.status)


def _set_status(row: SurveyAssignment, status: str) -> None:
    if status == COMPLETED and row.status != COMPLETED:
        row.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.status = status


@dataclass
class AssignResult:
    assigned: int = 0
    # users without a participant in surveylite
    without_participant: list = field(default_factory=list)


def assign_survey(
    db: Session, survey: surveylite_api.Survey, user_ids: list[int]
) -> AssignResult:
    """Gives the survey to the users. Raises SurveyliteError if surveylite fails."""

    result = AssignResult()
    participants = {}
    for user_id in user_ids:
        entry = participant_of(db, user_id)
        if entry is None:
            result.without_participant.append(user_id)
        else:
            participants[entry.surveylite_participant_id] = user_id
    if not participants:
        return result

    links = surveylite_api.assign(survey.id, list(participants))
    for link in links:
        user_id = participants.get(link.participant_id)
        if user_id is not None:
            _store_link(db, user_id, survey.title, link)
            result.assigned += 1
    db.commit()
    logger.info("Survey %s was given to %s users", survey.id, result.assigned)
    return result


def refresh_user(db: Session, user_id: int) -> list[SurveyAssignment]:
    """Reads the status of the surveys of a user from surveylite.

    If surveylite does not answer, the last known status stays.
    """

    entry = participant_of(db, user_id)
    if entry is not None:
        try:
            links = surveylite_api.participant_links(entry.surveylite_participant_id)
        except SurveyliteError as error:
            logger.warning("Survey status of user %s not read: %s", user_id, error)
        else:
            known = {row.survey_id: row for row in assignments_of(db, user_id)}
            for link in links:
                row = known.get(link.survey_id)
                if row is None:
                    # given in surveylite itself: show it here, too
                    _store_link(db, user_id, "", link)
                else:
                    _set_link(row, link)
            db.commit()
        if not entry.surveylite_login_url:
            # participant from before SurveyLite had login links
            try:
                entry.surveylite_login_url = surveylite_api.login_link(
                    entry.surveylite_participant_id
                )
                db.commit()
            except SurveyliteError as error:
                logger.warning("Login link of user %s not read: %s", user_id, error)
    return assignments_of(db, user_id)


def renew_login_link(db: Session, user_id: int) -> bool:
    """A new personal login link: the old link and the old survey links stop working.

    Raises SurveyliteError if SurveyLite fails. False: the user has no participant.
    """

    entry = participant_of(db, user_id)
    if entry is None:
        return False
    entry.surveylite_login_url = surveylite_api.login_link(
        entry.surveylite_participant_id, renew=True
    )
    db.commit()
    # the survey links with login carry the key of the login link
    refresh_user(db, user_id)
    return True


def refresh_all(db: Session) -> int:
    """Reads the status of all users. Returns the number of users."""

    entries = (
        db.query(SurveyliteService)
        .filter(
            SurveyliteService.deleted.is_(False), SurveyliteService.created.is_(True)
        )
        .all()
    )
    for user_id in {entry.user_id for entry in entries}:
        refresh_user(db, user_id)
    return len(entries)


# ---------- surveys that a service needs ----------


def requirements(db: Session) -> dict[str, ServiceRequirement]:
    return {row.service: row for row in db.query(ServiceRequirement).all()}


def set_requirement(
    db: Session, service: str, survey: surveylite_api.Survey | None
) -> None:
    """The service needs this completed survey (None: no survey needed)"""

    row = db.get(ServiceRequirement, service)
    if survey is None:
        if row is not None:
            db.delete(row)
    else:
        if row is None:
            row = ServiceRequirement(service=service, survey_id=survey.id)
            db.add(row)
        row.survey_id = survey.id
        row.survey_title = survey.title
    db.commit()


@dataclass(frozen=True)
class Blocked:
    """The service waits for this survey"""

    survey_id: int
    title: str
    # personal link of the user, None if the survey was not given to the user
    url: str | None
    status: str


def blocked_services(
    db: Session, user_id: int, assignments: list[SurveyAssignment] | None = None
) -> dict[str, Blocked]:
    """Services that the user cannot use yet: service -> the missing survey"""

    rules = requirements(db)
    if not rules:
        return {}
    if assignments is None:
        assignments = assignments_of(db, user_id)
    by_survey = {row.survey_id: row for row in assignments}
    blocked = {}
    for service, rule in rules.items():
        row = by_survey.get(rule.survey_id)
        if row is None or row.status != COMPLETED:
            blocked[service] = Blocked(
                survey_id=rule.survey_id,
                title=(row.survey_title if row else None)
                or rule.survey_title
                or f"Survey {rule.survey_id}",
                url=survey_link(row) if row else None,
                status=row.status if row else "not_given",
            )
    return blocked
