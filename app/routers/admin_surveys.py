"""Admin pages of sqlmate and SurveyLite: accounts, surveys and the surveys that services need"""

import logging

from fastapi import APIRouter, Depends, Form

from app import provisioning, surveys
from app.config import get_settings
from app.models import SurveyAssignment
from app.routers.admin import get_course_user, user_rows
from app.security import csrf_protect
from app.service_settings import DEPRECATED_SERVICES, SERVICE_INFO, SERVICES
from app.services import sqlmate_api, surveylite_api
from app.users import get_user_services
from app.web import Page, flash, redirect, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/mtas-admin/services",
    include_in_schema=False,
    dependencies=[Depends(require_admin)],
)

SQLMATE_PAGE = "/mtas-admin/services/sqlmate"
SURVEYLITE_PAGE = "/mtas-admin/services/surveylite"


def _api_state(check) -> dict:
    """{"ok": bool, "text": str} of an API check"""

    try:
        return {"ok": True, "text": check()}
    except (sqlmate_api.SqlmateError, surveylite_api.SurveyliteError) as error:
        return {"ok": False, "text": str(error)}


def _mark_deleted(db, entry) -> None:
    if entry is not None:
        entry.deleted = True
        db.commit()


# ---------- sqlmate ----------


@router.get("/sqlmate")
def sqlmate_page(page: Page = Depends()):
    settings = get_settings()
    api = _api_state(lambda: f"API key “{sqlmate_api.ping()}” works")
    rules = surveys.requirements(page.db)
    rows = user_rows(page.db)
    for row in rows:
        user_id = row["user"].itid
        row["entry"] = get_user_services(page.db, user_id).get("sqlmate")
        row["blocked"] = (
            surveys.blocked_services(page.db, user_id).get("sqlmate")
            if "sqlmate" in rules
            else None
        )
    return page.render(
        "admin/sqlmate.html",
        rows=rows,
        api=api,
        api_url=settings.sqlmate_api_url,
        public_url=settings.sqlmate_public_url,
        rule=rules.get("sqlmate"),
    )


@router.post("/sqlmate/create", dependencies=[Depends(csrf_protect)])
def sqlmate_create(page: Page = Depends(), user_id: int = Form(...)):
    """Creates the sqlmate account of a user (again, if the last try failed)"""

    student = get_course_user(page.db, user_id)
    entry = get_user_services(page.db, student.itid).get("sqlmate")
    if entry is not None and entry.created:
        flash(page.request, f"{student.email} already has a sqlmate account.", "info")
        return redirect(SQLMATE_PAGE)
    _mark_deleted(page.db, entry)
    if provisioning.sqlmate_user(
        page.db, student.itid, student.internal_email, force_create=True
    ):
        flash(page.request, f"sqlmate was set up for {student.email}.", "success")
    else:
        flash(
            page.request,
            f"sqlmate was not set up for {student.email}: see the log of the app.",
            "danger",
        )
    return redirect(SQLMATE_PAGE)


# ---------- SurveyLite ----------


def _requirement_services() -> list:
    """Services that can wait for a survey"""

    return [
        info
        for info in SERVICES
        if info.key not in DEPRECATED_SERVICES and info.key != "surveylite"
    ]


@router.get("/surveylite")
def surveylite_page(page: Page = Depends()):
    settings = get_settings()
    survey_list = []
    api = _api_state(lambda: "")
    try:
        survey_list = surveylite_api.list_surveys()
        api["text"] = f"{len(survey_list)} surveys"
    except surveylite_api.SurveyliteError as error:
        api = {"ok": False, "text": str(error)}

    counts = {}
    for row in page.db.query(SurveyAssignment).all():
        given, completed = counts.get(row.survey_id, (0, 0))
        counts[row.survey_id] = (
            given + 1,
            completed + (row.status == surveylite_api.COMPLETED),
        )

    rows = user_rows(page.db)
    for row in rows:
        user_id = row["user"].itid
        row["entry"] = surveys.participant_of(page.db, user_id)
        row["assignments"] = surveys.assignments_of(page.db, user_id)

    return page.render(
        "admin/surveylite.html",
        api=api,
        api_url=settings.surveylite_api_url,
        public_url=settings.surveylite_public_url,
        surveys=survey_list,
        counts=counts,
        rows=rows,
        rules=surveys.requirements(page.db),
        rule_services=_requirement_services(),
        status_text=surveys.STATUS_TEXT,
    )


def _find_survey(survey_id: int) -> surveylite_api.Survey | None:
    return next(
        (item for item in surveylite_api.list_surveys() if item.id == survey_id), None
    )


@router.post("/surveylite/participant", dependencies=[Depends(csrf_protect)])
def surveylite_create(page: Page = Depends(), user_id: int = Form(...)):
    """Creates the anonymous participant of a user (again, if the last try failed)"""

    student = get_course_user(page.db, user_id)
    if surveys.participant_of(page.db, student.itid) is not None:
        flash(page.request, f"{student.email} already has a participant.", "info")
        return redirect(SURVEYLITE_PAGE)
    _mark_deleted(page.db, get_user_services(page.db, student.itid).get("surveylite"))
    if provisioning.surveylite_participant(page.db, student.itid, force_create=True):
        flash(page.request, f"SurveyLite was set up for {student.email}.", "success")
    else:
        flash(
            page.request,
            f"SurveyLite was not set up for {student.email}: see the log of the app.",
            "danger",
        )
    return redirect(SURVEYLITE_PAGE)


@router.post("/surveylite/login-link", dependencies=[Depends(csrf_protect)])
def surveylite_login_link(page: Page = Depends(), user_id: int = Form(...)):
    """A new personal login link for a user: the old links stop working"""

    student = get_course_user(page.db, user_id)
    try:
        renewed = surveys.renew_login_link(page.db, student.itid)
    except surveylite_api.SurveyliteError as error:
        flash(page.request, f"The login link was not renewed: {error}", "danger")
        return redirect(SURVEYLITE_PAGE)
    if renewed:
        flash(
            page.request,
            f"{student.email} has a new login link. The old links stop working.",
            "success",
        )
    else:
        flash(page.request, f"{student.email} has no participant.", "info")
    return redirect(SURVEYLITE_PAGE)


@router.post("/surveylite/assign", dependencies=[Depends(csrf_protect)])
def surveylite_assign(
    page: Page = Depends(), survey_id: int = Form(...), user_id: str = Form("all")
):
    """Gives a survey to one user or to all users with a participant"""

    try:
        survey = _find_survey(survey_id)
        if survey is None:
            flash(page.request, f"There is no survey {survey_id}.", "danger")
            return redirect(SURVEYLITE_PAGE)
        if user_id == "all":
            user_ids = [row["user"].itid for row in user_rows(page.db)]
        else:
            user_ids = [get_course_user(page.db, int(user_id)).itid]
        result = surveys.assign_survey(page.db, survey, user_ids)
    except surveylite_api.SurveyliteError as error:
        flash(page.request, f"The survey was not given: {error}", "danger")
        return redirect(SURVEYLITE_PAGE)

    message = f"“{survey.title}” was given to {result.assigned} users."
    if result.without_participant:
        message += (
            f" {len(result.without_participant)} users have no SurveyLite "
            "participant: set it up first."
        )
    flash(page.request, message, "warning" if result.without_participant else "success")
    return redirect(SURVEYLITE_PAGE)


@router.post("/surveylite/refresh", dependencies=[Depends(csrf_protect)])
def surveylite_refresh(page: Page = Depends()):
    """Reads the status of the surveys of all users"""

    count = surveys.refresh_all(page.db)
    flash(page.request, f"The status of {count} participants was read.", "success")
    return redirect(SURVEYLITE_PAGE)


@router.post("/surveylite/requirement", dependencies=[Depends(csrf_protect)])
def surveylite_requirement(
    page: Page = Depends(), service: str = Form(...), survey_id: str = Form("")
):
    """A service waits for a completed survey (empty: no survey needed)"""

    if service not in {info.key for info in _requirement_services()}:
        flash(page.request, f"There is no service “{service}”.", "danger")
        return redirect(SURVEYLITE_PAGE)
    name = SERVICE_INFO[service].name
    if not survey_id:
        surveys.set_requirement(page.db, service, None)
        flash(page.request, f"{name} needs no survey now.", "success")
        return redirect(SURVEYLITE_PAGE)

    try:
        survey = _find_survey(int(survey_id))
    except (ValueError, surveylite_api.SurveyliteError) as error:
        flash(page.request, f"Not saved: {error}", "danger")
        return redirect(SURVEYLITE_PAGE)
    if survey is None:
        flash(page.request, f"There is no survey {survey_id}.", "danger")
        return redirect(SURVEYLITE_PAGE)
    surveys.set_requirement(page.db, service, survey)
    flash(
        page.request,
        f"{name} opens for a user after the survey “{survey.title}”. "
        "Give the survey to the users, if not done yet.",
        "success",
    )
    return redirect(SURVEYLITE_PAGE)
