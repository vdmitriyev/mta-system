"""Admin pages (for the e-mail addresses in SYSTEM_ADMINS)"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

import psutil
import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app import config, provisioning
from app.config import get_settings
from app.exercises import (
    PART_BONUS,
    PART_REVIEW,
    get_exercise,
    get_exercises,
    get_latest_bonus_points,
    get_latest_review,
    get_user_bonus_points,
    get_user_reviews,
    render_review_content,
)
from app.models import (
    SERVICE_MODELS,
    ExerciseBonusPoints,
    ExerciseReviews,
    Users,
)
from app.security import csrf_protect, random_string
from app.service_settings import (
    DEPRECATED_SERVICES,
    SERVICE_INFO,
    ServiceSettingError,
    service_setting_rows,
    set_creates_accounts,
)
from app.services import (
    docker_ctl,
    metabase_api,
    nifi_api,
    openrefine_api,
    postgresql,
    wordpress_api,
)
from app.tasks import TaskError, enqueue, recent_tasks
from app.users import (
    access_url,
    container_name,
    course_users,
    email_to_name,
    generate_accounts_task,
    get_user_services,
)
from app.visibility import change_ui_visibility_settings, grouped_visibility_rows
from app.web import Page, flash, redirect, require_admin

# Services with an own container per user that the admin can manage
MANAGED_SERVICES = {"metabase": "Metabase", "openrefine": "OpenRefine"}
IMAGE_CHECKS = {
    "metabase": metabase_api.check_image,
    "openrefine": openrefine_api.check_image,
}
PORT_OFFSETS = {
    "metabase": config.METABASE_PORT_OFFSET,
    "openrefine": config.OPENREFINE_PORT_OFFSET,
}
MAX_ACCOUNTS_PER_REQUEST = 50

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/mtas-admin", include_in_schema=False, dependencies=[Depends(require_admin)]
)


def user_rows(db: Session) -> list:
    """Users of the course with name and login link"""

    return [
        {
            "user": user,
            "name": email_to_name(user.email),
            "access_url": access_url(user),
        }
        for user in course_users(db)
    ]


def get_course_user(db: Session, user_id) -> Users:
    user = db.query(Users).filter(Users.itid == user_id).first()
    if user is None:
        raise HTTPException(status_code=404)
    return user


@router.get("/")
def overview(page: Page = Depends()):
    users = course_users(page.db)
    service_counts = {
        name: page.db.query(model).filter(model.deleted.is_(False)).count()
        for name, model in SERVICE_MODELS.items()
    }
    return page.render(
        "admin/overview.html",
        users_total=len(users),
        users_assigned=sum(1 for user in users if user.is_user_assigned),
        service_counts={k: v for k, v in service_counts.items() if v},
        tasks=recent_tasks(page.db, limit=15),
        accounts_to_create=get_settings().max_user_accounts_to_create,
    )


@router.post("/accounts/generate", dependencies=[Depends(csrf_protect)])
def generate_accounts(background_tasks: BackgroundTasks, page: Page = Depends()):
    """Prepares accounts with all services. New users get them without waiting."""

    count = min(get_settings().max_user_accounts_to_create, MAX_ACCOUNTS_PER_REQUEST)
    enqueue(
        background_tasks,
        page.db,
        "accounts:generate",
        generate_accounts_task,
        count,
        user_id=page.user.itid,
    )
    flash(page.request, f"{count} accounts are prepared in the background.", "success")
    return redirect("/mtas-admin/")


@router.get("/users")
def users_page(page: Page = Depends()):
    rows = user_rows(page.db)
    for row in rows:
        row["services"] = sorted(get_user_services(page.db, row["user"].itid))
    return page.render("admin/users.html", rows=rows)


@router.get("/reviews")
def reviews_page(page: Page = Depends()):
    exercises = get_exercises(page.db, part=PART_REVIEW)
    rows = user_rows(page.db)
    for row in rows:
        row["reviews"] = get_user_reviews(page.db, exercises, row["user"].itid)
    return page.render("admin/reviews.html", rows=rows, exercises=exercises)


def _review_edit(page: Page, user_id, exercise_code: str):
    exercise = get_exercise(page.db, exercise_code)
    if exercise is None:
        raise HTTPException(status_code=404)
    student = get_course_user(page.db, user_id)
    review = get_latest_review(page.db, student.itid, exercise.itid)
    return page.render(
        "admin/review_edit.html",
        student=student,
        student_name=email_to_name(student.email),
        exercise=exercise,
        review=review,
        preview=render_review_content(review) if review else None,
    )


@router.get("/reviews/edit")
def review_edit_form(user: int, exercise: str, page: Page = Depends()):
    return _review_edit(page, user, exercise)


@router.post("/reviews/edit", dependencies=[Depends(csrf_protect)])
def review_edit(
    page: Page = Depends(),
    user: int = Form(...),
    exercise: str = Form(...),
    content: str = Form(""),
    submitted: bool = Form(False),
    reviewed: bool = Form(False),
    visible: bool = Form(False),
):
    exercise_db = get_exercise(page.db, exercise)
    if exercise_db is None:
        raise HTTPException(status_code=404)
    student = get_course_user(page.db, user)

    page.db.add(
        ExerciseReviews(
            content=content,
            user_id=student.itid,
            exercise_id=exercise_db.itid,
            submitted=submitted,
            reviewed=reviewed,
            visible=visible,
        )
    )
    page.db.commit()
    flash(page.request, "The review was saved.", "success")
    return redirect(f"/mtas-admin/reviews/edit?user={student.itid}&exercise={exercise}")


@router.get("/bonus")
def bonus_page(page: Page = Depends()):
    exercises = get_exercises(page.db, part=PART_BONUS)
    rows = user_rows(page.db)
    for row in rows:
        row["bonuses"], row["bonus_total"] = get_user_bonus_points(
            page.db, exercises, row["user"].itid
        )
    return page.render("admin/bonus.html", rows=rows, exercises=exercises)


def _bonus_edit(page: Page, user_id, exercise_code: str, status_code=200, error=None):
    exercise = get_exercise(page.db, exercise_code)
    if exercise is None:
        raise HTTPException(status_code=404)
    student = get_course_user(page.db, user_id)
    return page.render(
        "admin/bonus_edit.html",
        status_code=status_code,
        student=student,
        student_name=email_to_name(student.email),
        exercise=exercise,
        bonus=get_latest_bonus_points(page.db, student.itid, exercise.itid),
        error=error,
    )


@router.get("/bonus/edit")
def bonus_edit_form(user: int, exercise: str, page: Page = Depends()):
    return _bonus_edit(page, user, exercise)


@router.post("/bonus/edit", dependencies=[Depends(csrf_protect)])
def bonus_edit(
    page: Page = Depends(),
    user: int = Form(...),
    exercise: str = Form(...),
    points: str = Form(""),
    visible: bool = Form(False),
    is_addable: bool = Form(False),
):
    exercise_db = get_exercise(page.db, exercise)
    if exercise_db is None:
        raise HTTPException(status_code=404)
    student = get_course_user(page.db, user)

    try:
        value = float(points.replace(",", "."))
    except ValueError:
        return _bonus_edit(
            page, user, exercise, status_code=400, error="Enter the points as a number."
        )

    page.db.add(
        ExerciseBonusPoints(
            user_id=student.itid,
            exercise_id=exercise_db.itid,
            points=value,
            is_addable=is_addable,
            visible=visible,
        )
    )
    page.db.commit()
    flash(page.request, "The bonus points were saved.", "success")
    return redirect(f"/mtas-admin/bonus/edit?user={student.itid}&exercise={exercise}")


def _managed_service(service: str) -> str:
    if service not in MANAGED_SERVICES:
        raise HTTPException(status_code=404)
    return service


@router.get("/services/{service}")
def service_page(service: str, page: Page = Depends(), check: str | None = None):
    """Containers of the users. OpenRefine: ?check=access requests each container."""

    _managed_service(service)
    rows = user_rows(page.db)
    for row in rows:
        entry = get_user_services(page.db, row["user"].itid).get(service)
        row["entry"] = entry
        row["container"] = container_name(service, entry) if entry else None
    statuses = docker_ctl.container_statuses([row["container"] for row in rows])
    for row in rows:
        row["status"] = statuses.get(row["container"], docker_ctl.UNKNOWN)

    access_checked = service == "openrefine" and check == "access"
    if access_checked:
        check_openrefine_access(rows)
    return page.render(
        "admin/service.html",
        rows=rows,
        service=service,
        service_title=MANAGED_SERVICES[service],
        image=IMAGE_CHECKS[service](ask_registry=False),
        can_check_access=service == "openrefine",
        access_checked=access_checked,
    )


def account_number(user: Users) -> int:
    """Number of the account (see next_account_number), read from the internal e-mail"""

    try:
        return int(user.internal_email.split("@")[0].rsplit("_", 1)[-1])
    except ValueError:
        raise TaskError("The account of this user has no number")


def create_service_task(db: Session, service: str, user_id: int) -> str:
    """Background task: creates the container of a user again.

    The old container is stopped and renamed, the old account is marked as deleted.
    """

    user = db.query(Users).filter(Users.itid == user_id).first()
    if user is None:
        raise TaskError("No such user")

    services = get_user_services(db, user.itid)
    number = account_number(user)
    port = number + PORT_OFFSETS[service]

    old = services.get(service)
    if "postgresql" in services:
        password = services["postgresql"].postgresql_password
    elif old is not None:
        password = getattr(old, f"{service}_password")
    else:
        password = random_string()

    # before the old container is stopped: without the image no new one can start
    image = IMAGE_CHECKS[service]()
    if not image.ok:
        raise TaskError(f"{MANAGED_SERVICES[service]} was not created: {image.text}")

    name = docker_ctl.container_name(service, port)
    docker_ctl.retire_container(name, f"{name}-{uuid.uuid4().hex[:8]}")
    model = SERVICE_MODELS[service]
    db.query(model).filter(model.user_id == user.itid).update(
        {"deleted": True, "created": False}
    )
    db.commit()

    if service == "metabase":
        is_created = provisioning.metabase_user(
            db, user.itid, user.internal_email, password, port, force_create=True
        )
    else:
        is_created = provisioning.openrefine_user(
            db,
            user.itid,
            f"{config.OPENREFINE_USER_PREFIX}_{str(number).zfill(2)}",
            password,
            port,
            force_create=True,
        )

    title = MANAGED_SERVICES[service]
    if not is_created:
        raise TaskError(f"{title} was not created for {user.email}")
    return f"{title} was created for {user.email}"


@router.post("/services/{service}/{action}", dependencies=[Depends(csrf_protect)])
def service_action(
    service: str,
    action: str,
    background_tasks: BackgroundTasks,
    page: Page = Depends(),
    user_id: int = Form(...),
):
    _managed_service(service)
    title = MANAGED_SERVICES[service]
    student = get_course_user(page.db, user_id)
    back = redirect(f"/mtas-admin/services/{service}")

    if action == "create":
        enqueue(
            background_tasks,
            page.db,
            f"service:create:{service}",
            create_service_task,
            service,
            student.itid,
            user_id=page.user.itid,
        )
        flash(
            page.request,
            f"{title} is created for {student.email} in the background. "
            "See the tasks on the overview page.",
            "success",
        )
        return back

    if action not in ("start", "stop"):
        raise HTTPException(status_code=404)

    entry = get_user_services(page.db, student.itid).get(service)
    container = container_name(service, entry) if entry else None
    if docker_ctl.run_action(container, action):
        flash(
            page.request, f"{title} of {student.email}: {action} was sent.", "success"
        )
    else:
        flash(
            page.request,
            f"{title} of {student.email}: {action} failed. Is there a container?",
            "danger",
        )
    return back


def server_summary() -> dict:
    megabyte = 1024 * 1024
    memory = psutil.virtual_memory()
    return {
        "containers": docker_ctl.containers_summary(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": memory.percent,
        "memory_total_mb": round(memory.total / megabyte),
        "memory_used_mb": round(memory.used / megabyte),
        "memory_available_mb": round(memory.available / megabyte),
    }


@router.get("/monitoring")
def monitoring_page(page: Page = Depends()):
    return page.render(
        "admin/monitoring.html",
        summary=server_summary(),
        containers=docker_ctl.containers_info(),
    )


def grouped_settings() -> dict:
    """Settings without secrets, grouped by the first word of the name.

    The names and ports of the accounts (*_PREFIX, *_OFFSET) are in the block of their service.
    """

    groups = {}
    for key, value in get_settings().public_items().items():
        groups.setdefault(key.split("_")[0], []).append((key, value))

    general = []
    for group in [name for name, items in groups.items() if len(items) == 1]:
        general.extend(groups.pop(group))

    for name in sorted(dir(config)):
        if name.endswith(("_PREFIX", "_OFFSET")):
            groups.setdefault(name.split("_")[0], []).append(
                (name, getattr(config, name))
            )

    result = {"GENERAL": sorted(general)} if general else {}
    result.update({name: groups[name] for name in sorted(groups)})
    return result


@router.get("/settings")
def settings_page(page: Page = Depends()):
    return page.render("admin/settings.html", groups=grouped_settings())


@router.get("/configs")
def old_settings_address():
    """Old address of the settings page"""

    return redirect("/mtas-admin/settings")


@router.get("/visibility")
def visibility_page(page: Page = Depends()):
    return page.render(
        "admin/visibility.html",
        categories=grouped_visibility_rows(page.db),
        deprecated={SERVICE_INFO[key].name for key in DEPRECATED_SERVICES},
    )


@router.post("/visibility", dependencies=[Depends(csrf_protect)])
def visibility_change(
    page: Page = Depends(), ui_key: str = Form(...), visible: bool = Form(...)
):
    if change_ui_visibility_settings(page.db, ui_key, visible):
        state = "shown" if visible else "hidden"
        flash(page.request, f"“{ui_key}” is now {state}.", "success")
    else:
        flash(page.request, f"There is no setting “{ui_key}”.", "danger")
    return redirect("/mtas-admin/visibility")


@router.get("/auto-creation")
def auto_creation_page(page: Page = Depends()):
    return page.render(
        "admin/auto_creation.html",
        rows=service_setting_rows(page.db),
        info=SERVICE_INFO,
        images=container_images(),
    )


def container_images() -> dict:
    """Images of the services whose version is known (versions.env): service -> images"""

    settings = get_settings()
    return {
        "postgresql": [postgresql.image()],
        "pgadmin4": [f"dpage/pgadmin4:{settings.pgadmin4_version}"],
        "metabase": [metabase_api.image()],
        "openrefine": [openrefine_api.image()],
        "mariadb": [f"mariadb:{settings.mariadb_version}"],
        "wordpress": [wordpress_api.image(), wordpress_api.cli_image()],
        "sqlmate": [f"sqlmate:{settings.sqlmate_version}"],
        "surveylite": [f"surveylite:{settings.surveylite_version}"],
        "nifi": [nifi_api.IMAGE],
    }


@router.post("/auto-creation", dependencies=[Depends(csrf_protect)])
def auto_creation_change(
    page: Page = Depends(), service: str = Form(...), on: bool = Form(...)
):
    try:
        set_creates_accounts(page.db, service, on)
    except ServiceSettingError as error:
        flash(page.request, str(error), "danger")
    else:
        name = SERVICE_INFO[service].name
        state = "now creates" if on else "no longer creates"
        flash(
            page.request,
            f"The app {state} an account in {name} for new users.",
            "success",
        )
    return redirect("/mtas-admin/auto-creation")


@router.get("/service-accounts")
def old_auto_creation_address():
    """Old address of the page "Auto creation" """

    return redirect("/mtas-admin/auto-creation")


def check_basic_auth(url: str, login: str, password: str) -> str:
    """Requests the URL with the login. Returns the HTTP status or the kind of error."""

    try:
        # nginx can use a self-signed certificate
        response = requests.get(
            url, auth=(login, password), verify=False, timeout=4  # nosec B501
        )
        return str(response.status_code)
    except requests.exceptions.Timeout:
        return "TIMEOUT"
    except requests.exceptions.ConnectionError:
        return "DOWN"
    except Exception:
        logger.exception("Basic auth check failed: %s", url)
        return "ERROR"


def check_openrefine_access(rows: list) -> None:
    """Requests the OpenRefine container of each user with the login of the user.

    Sets row["access"]: the HTTP status ("200" works) or the kind of error.
    """

    settings = get_settings()
    jobs = []
    for row in rows:
        entry = row["entry"]
        if entry is None:
            row["access"] = "NO SERVICE"
        elif entry.openrefine_docker_port is None:
            row["access"] = "NO PORT"
        else:
            url = settings.container_url("openrefine", entry.openrefine_docker_port)
            jobs.append((row, url, entry.openrefine_user, entry.openrefine_password))

    with ThreadPoolExecutor(max_workers=8) as executor:
        verdicts = executor.map(lambda job: check_basic_auth(*job[1:]), jobs)
        for (row, *_), verdict in zip(jobs, verdicts):
            row["access"] = verdict


@router.get("/basic-auth-check")
def basic_auth_check_page():
    """Old address: the check is on the OpenRefine page now"""

    return redirect("/mtas-admin/services/openrefine?check=access")
