"""Pages of a logged-in user: services, dataset import, reviews, bonus points"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app import surveys
from app.config import get_settings
from app.exercises import (
    PART_BONUS,
    PART_REVIEW,
    get_exercises,
    get_user_bonus_points,
    get_user_reviews,
)
from app.importers import DATASETS, import_dataset_task, import_kind
from app.models import CONTAINER_SERVICES, BackgroundTask, Users
from app.security import csrf_protect
from app.services import docker_ctl
from app.tasks import ACTIVE, active_task, enqueue
from app.users import container_name, get_user_services, postgresql_uri
from app.web import Page, flash, redirect, require_user

NIFI_DRIVER_CLASS = "org.postgresql.Driver"
NIFI_DRIVER_LOCATION = "/opt/nifi/nifi-current/lib/postgresql-42.2.18.jar"

logger = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)


def _field(
    label: str,
    value,
    copy: bool = True,
    secret: bool = False,
    link=False,
    link_text: str | None = None,
):
    return {
        "label": label,
        "value": value,
        "can_copy": copy,
        "secret": secret,
        "link": link,
        # text of the link instead of the address (e.g. for a personal login link)
        "link_text": link_text,
    }


def _filled(fields: list) -> list:
    """The fields that have a value (e.g. no login link from an older SurveyLite)"""

    return [field for field in fields if field["value"]]


def service_cards(page: Page, user: Users) -> list:
    """Builds the cards of the services page, in the order of SERVICES_UI"""

    settings = get_settings()
    visibility = page.visibility
    services = get_user_services(page.db, user.itid)
    statuses = docker_ctl.container_statuses(
        [
            container_name(name, services[name])
            for name in CONTAINER_SERVICES
            if name in services
        ]
    )
    pg = services.get("postgresql")
    # status of the surveys from surveylite: some services wait for a survey
    assignments = (
        surveys.refresh_user(page.db, user.itid)
        if "surveylite" in services
        else surveys.assignments_of(page.db, user.itid)
    )
    blocked = surveys.blocked_services(page.db, user.itid, assignments)

    def container_card(name: str, title: str, fields: list) -> dict:
        entry = services[name]
        container = container_name(name, entry)
        url = settings.container_url(name, getattr(entry, f"{name}_docker_port"))
        if name == "nifi":
            url += "nifi/"
        return {
            "name": name,
            "title": title,
            "fields": [_field("URL", url, copy=False, link=True), *fields],
            "status": statuses.get(container, docker_ctl.UNKNOWN),
            "can_start": bool(visibility.get(f"{name}_self_managment")),
        }

    builders = {
        "postgresql": lambda entry: {
            "name": "postgresql",
            "title": "PostgreSQL",
            "fields": [
                _field("Server", settings.postgresql_db_host),
                _field("Port", "5432", copy=False),
                _field("Database", entry.postgresql_db),
                _field("User", entry.postgresql_user),
                _field("Password", entry.postgresql_password, secret=True),
            ],
            "datasets": [
                {
                    "name": dataset,
                    "title": title,
                    "task": active_task(page.db, import_kind(dataset), user.itid),
                }
                for dataset, (title, _module) in DATASETS.items()
                if visibility.get(f"importers_{dataset}")
            ],
        },
        "pgadmin4": lambda entry: {
            "name": "pgadmin4",
            "title": "pgAdmin 4",
            "fields": [
                _field("URL", settings.pgadmin4_url, copy=False, link=True),
                _field("Login", entry.pgadmin4_user),
                _field("Password", entry.pgadmin4_password, secret=True),
            ],
        },
        "metabase": lambda entry: container_card(
            "metabase",
            "Metabase",
            [
                _field("Login", user.internal_email),
                _field("Password", entry.metabase_password, secret=True),
            ],
        ),
        "openrefine": lambda entry: container_card(
            "openrefine",
            "OpenRefine",
            [
                _field("Login", entry.openrefine_user),
                _field("Password", entry.openrefine_password, secret=True),
            ],
        ),
        "nifi": lambda entry: container_card(
            "nifi",
            "Apache NiFi",
            [
                _field("Login", entry.nifi_user),
                _field("Password", entry.nifi_password, secret=True),
                *(
                    [
                        _field(
                            "Database connection URL",
                            f"jdbc:postgresql://{settings.server_fqdn}:5432/{pg.postgresql_db}",
                        ),
                        _field("Database driver class name", NIFI_DRIVER_CLASS),
                        _field("Database driver location", NIFI_DRIVER_LOCATION),
                    ]
                    if pg
                    else []
                ),
            ],
        ),
        "mariadb": lambda entry: {
            "name": "mariadb",
            "title": "MariaDB",
            "fields": [
                _field("Server", settings.server_fqdn),
                _field("Port", "3306", copy=False),
                _field("Database", entry.mariadb_db),
                _field("User", entry.mariadb_user),
                _field("Password", entry.mariadb_password, secret=True),
            ],
        },
        "wordpress": lambda entry: container_card(
            "wordpress",
            "WordPress",
            [
                _field(
                    "URL (admin)",
                    settings.container_url("wordpress", entry.wordpress_docker_port)
                    + "wp-admin/",
                    copy=False,
                    link=True,
                ),
                _field("Login", entry.wordpress_login),
                _field("Password", entry.wordpress_password, secret=True),
            ],
        ),
        "superset": lambda entry: {
            "name": "superset",
            "title": "Apache Superset",
            "fields": [
                _field("URL", settings.superset_url, copy=False, link=True),
                _field("Login", entry.superset_user),
                _field("Password", entry.superset_password, secret=True),
                *(
                    [_field("SQLAlchemy URI", postgresql_uri(pg), secret=True)]
                    if pg
                    else []
                ),
            ],
        },
        "sqlmate": lambda entry: {
            "name": "sqlmate",
            "title": "sqlmate",
            "fields": (
                [
                    _field("URL", settings.sqlmate_public_url, copy=False, link=True),
                    _field(
                        "Login link",
                        entry.sqlmate_login_url,
                        link=True,
                        link_text="Log in to sqlmate",
                    ),
                    _field("Login", entry.sqlmate_login),
                    _field("PIN", entry.sqlmate_pin, secret=True),
                ]
                if entry.created
                else []
            ),
            "note": (
                None
                if entry.created
                else "Your account in sqlmate is not set up yet. Ask your instructor."
            ),
        },
        "surveylite": lambda entry: {
            "name": "surveylite",
            "title": "SurveyLite",
            "fields": (
                _filled(
                    [
                        _field(
                            "Your surveys",
                            settings.surveylite_public_url + "me",
                            copy=False,
                            link=True,
                        ),
                        _field(
                            "Login link",
                            surveys.public_link(entry.surveylite_login_url),
                            link=True,
                            link_text="Log in to SurveyLite",
                        ),
                        _field("Login", entry.surveylite_login),
                        _field("PIN", entry.surveylite_pin, secret=True),
                    ]
                )
                if entry.created
                else []
            ),
            "note": (
                "Your answers are anonymous: SurveyLite does not know who you are."
                if entry.created
                else "Your access to SurveyLite is not set up yet. Ask your instructor."
            ),
            "surveys": [
                {
                    "title": row.survey_title or f"Survey {row.survey_id}",
                    "url": surveys.survey_link(row),
                    "status": row.status,
                    "status_text": surveys.STATUS_TEXT.get(row.status, row.status),
                }
                for row in assignments
            ],
        },
        "jupyterhub": lambda entry: {
            "name": "jupyterhub",
            "title": "JupyterHub",
            "fields": [
                _field("URL", settings.jupyterhub_url, copy=False, link=True),
                _field("User", entry.jupyterhub_user),
                _field("Password", entry.jupyterhub_password, secret=True),
            ],
        },
    }

    cards = []
    for name in settings.services_ui:
        if name in builders and name in services and visibility.get(name):
            if name in blocked:
                cards.append(blocked_card(name, builders, services, blocked[name]))
            else:
                cards.append(builders[name](services[name]))
    return cards


def blocked_card(name: str, builders: dict, services: dict, missing) -> dict:
    """The card of a service that waits for a survey: no login, the survey instead"""

    card = builders[name](services[name])
    return {
        "name": name,
        "title": card["title"],
        "fields": [],
        "blocked": {
            "title": missing.title,
            "url": missing.url,
            "status_text": surveys.STATUS_TEXT.get(missing.status, ""),
        },
    }


def finished_imports(db: Session, user_id: int, limit: int = 3) -> list:
    """Gets the last dataset imports of the user that are done or failed"""

    return (
        db.query(BackgroundTask)
        .filter(
            BackgroundTask.user_id == user_id,
            BackgroundTask.kind.like("import:%"),
            BackgroundTask.status.not_in(ACTIVE),
        )
        .order_by(BackgroundTask.itid.desc())
        .limit(limit)
        .all()
    )


@router.get("/services")
def services_page(page: Page = Depends(), user: Users = Depends(require_user)):
    return page.render(
        "services.html",
        cards=service_cards(page, user),
        finished_imports=finished_imports(page.db, user.itid),
    )


@router.post("/services/{service}/start", dependencies=[Depends(csrf_protect)])
def start_service(
    service: str, page: Page = Depends(), user: Users = Depends(require_user)
):
    """Starts the container of the user for this service"""

    visibility = page.visibility
    entry = get_user_services(page.db, user.itid).get(service)
    if (
        service not in CONTAINER_SERVICES
        or entry is None
        or not visibility.get(service)
        or not visibility.get(f"{service}_self_managment")
    ):
        raise HTTPException(status_code=404)

    if docker_ctl.run_action(container_name(service, entry), "start"):
        flash(
            page.request,
            "The service starts. This can take a few minutes.",
            "success",
        )
    else:
        flash(
            page.request,
            "The service was not started. Ask your instructor for help.",
            "danger",
        )
    return redirect("/services")


@router.post("/importer", dependencies=[Depends(csrf_protect)])
def import_dataset(
    background_tasks: BackgroundTasks,
    page: Page = Depends(),
    user: Users = Depends(require_user),
    dataset: str = Form(""),
):
    """Imports a dataset into the PostgreSQL database of the user (in the background)"""

    if dataset not in DATASETS or not page.visibility.get(f"importers_{dataset}"):
        flash(page.request, "There is no such dataset.", "danger")
        return redirect("/services")

    if "postgresql" not in get_user_services(page.db, user.itid):
        flash(page.request, "You have no PostgreSQL database.", "danger")
        return redirect("/services")

    kind = import_kind(dataset)
    if active_task(page.db, kind, user.itid) is None:
        logger.info("Import of %s started for user %s", dataset, user.itid)
        enqueue(
            background_tasks,
            page.db,
            kind,
            import_dataset_task,
            user.itid,
            dataset,
            user_id=user.itid,
        )
    return redirect("/services")


@router.get("/reviews")
def reviews_page(page: Page = Depends(), user: Users = Depends(require_user)):
    exercises = get_exercises(page.db, part=PART_REVIEW, only_visible=True)
    return page.render(
        "reviews.html", reviews=get_user_reviews(page.db, exercises, user.itid)
    )


@router.get("/bonus")
def bonus_page(page: Page = Depends(), user: Users = Depends(require_user)):
    exercises = get_exercises(page.db, part=PART_BONUS)
    bonuses, total = get_user_bonus_points(page.db, exercises, user.itid)
    return page.render("bonus.html", bonuses=bonuses, bonus_total=total)
