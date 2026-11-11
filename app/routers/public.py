"""Pages for everybody: home, about, registration, login"""

import logging

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request

from app.captcha import generate_captcha
from app.config import get_settings
from app.security import AttemptLimiter, csrf_protect, make_hash, verify_hash
from app.service_settings import DEPRECATED_SERVICES
from app.tasks import enqueue, get_task
from app.users import (
    email_hash,
    is_email_in_allowed_fqdn_list,
    pin_hash,
    register_user_task,
    validate_credentials,
)
from app.web import Page, flash, login_user, logout_user, redirect

SESSION_CAPTCHA_KEY = "captcha"
REGISTRATION_KIND = "registration"

logger = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)
login_limiter = AttemptLimiter(max_attempts=10, window_seconds=15 * 60)


@router.get("/")
@router.get("/index")
def index(page: Page = Depends()):
    return page.render("index.html")


# services on the About page: key, name, image, text
ABOUT_SERVICES = [
    (
        "pgadmin4",
        "pgAdmin 4",
        "pgadmin4-screen.png",
        "Web interface to manage PostgreSQL databases.",
    ),
    (
        "postgresql",
        "PostgreSQL",
        "postgresql-logo.png",
        "Relational database. Each user gets an own database.",
    ),
    (
        "metabase",
        "Metabase",
        "metabase-screen.png",
        "Dashboards and questions on your data.",
    ),
    (
        "openrefine",
        "OpenRefine",
        "openrefine-screen.png",
        "Tool to clean and transform data.",
    ),
    (
        "mariadb",
        "MariaDB",
        "mariadb-logo.svg",
        "Relational database for WordPress. Each user gets an own database.",
    ),
    (
        "wordpress",
        "WordPress",
        "wordpress-logo.svg",
        "Your own website with WordPress.",
    ),
    ("nifi", "Apache NiFi", "nifi-screen.png", "Data flows between systems."),
    (
        "jupyterhub",
        "JupyterHub",
        "jupyterhub-screen.png",
        "Jupyter Notebooks for Python in a browser.",
    ),
]

ABOUT_ICONS = {"mariadb": "database", "wordpress": "edit"}


def about_services() -> list[dict]:
    """The services with the versions of versions.env (none for deprecated services)"""

    settings = get_settings()
    services = []
    for key, name, image, text in ABOUT_SERVICES:
        deprecated = key in DEPRECATED_SERVICES
        services.append(
            {
                "name": name,
                "image": image,
                # without an image: an icon on the card
                "icon": ABOUT_ICONS.get(key, "box"),
                "text": text,
                "status": "deprecated" if deprecated else "supported",
                "version": (
                    None if deprecated else getattr(settings, f"{key}_version", None)
                ),
            }
        )
    return services


@router.get("/about")
def about(page: Page = Depends()):
    return page.render("about.html", services=about_services())


def _registration_form(page: Page, email: str = "", error: str = None):
    """Shows the registration form with a new captcha"""

    captcha_txt, captcha_png = generate_captcha(add_noise=True)
    page.request.session[SESSION_CAPTCHA_KEY] = make_hash(
        captcha_txt, get_settings().hash_key_hidden.get_secret_value()
    )
    return page.render(
        "register.html",
        status_code=400 if error else 200,
        captcha_image=captcha_png,
        email=email,
        error=error,
    )


def registration_error(email: str, code: str, captcha: str, captcha_hash: str):
    """Checks the registration form. Returns the error text (None if all is right)."""

    settings = get_settings()
    if not email:
        return "Enter your e-mail address."
    try:
        validate_email(email, check_deliverability=False, allow_smtputf8=False)
    except EmailNotValidError as error:
        return f"This e-mail address is not valid: {error}"
    if not is_email_in_allowed_fqdn_list(email, settings.allowed_fqdn_for_emails):
        return "Use the e-mail address of your organization."
    if code.strip().upper() != settings.course_security_code.upper():
        return "The course code is not correct. Ask your instructor for it."
    if not verify_hash(
        captcha.strip(), captcha_hash, settings.hash_key_hidden.get_secret_value()
    ):
        return "The captcha is not correct. Enter the digits of the new picture."
    return None


@router.get("/register")
def register_form(page: Page = Depends()):
    return _registration_form(page)


@router.post("/register", dependencies=[Depends(csrf_protect)])
def register(
    background_tasks: BackgroundTasks,
    page: Page = Depends(),
    email: str = Form(""),
    code: str = Form(""),
    captcha: str = Form(""),
):
    email = email.strip().lower()
    # each captcha is valid for one attempt
    captcha_hash = page.request.session.pop(SESSION_CAPTCHA_KEY, None)

    error = registration_error(email, code, captcha, captcha_hash)
    if error:
        logger.warning("Registration of %s was rejected: %s", email, error)
        return _registration_form(page, email=email, error=error)

    logger.info("Registration started: %s", email)
    task = enqueue(
        background_tasks, page.db, REGISTRATION_KIND, register_user_task, email
    )
    return redirect(f"/register/status/{task.public_id}")


@router.get("/register/status/{task_id}")
def register_status(task_id: str, page: Page = Depends()):
    task = get_task(page.db, task_id)
    if task is None or task.kind != REGISTRATION_KIND:
        return page.render(
            "error.html",
            status_code=404,
            title="Registration not found",
            detail="This registration does not exist. Register again.",
        )
    return page.render("register_status.html", task=task)


def _login_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}|{email}"


def _login(page: Page, u_hash: str, p_hash: str, limiter_key: str, email: str = ""):
    if login_limiter.is_blocked(limiter_key):
        return page.render(
            "login.html",
            status_code=429,
            email=email,
            error="Too many failed logins. Wait 15 minutes and try again.",
        )

    user = validate_credentials(page.db, u_hash, p_hash)
    if user is None:
        login_limiter.add_failure(limiter_key)
        return page.render(
            "login.html",
            status_code=401,
            email=email,
            error="The e-mail or the PIN is not correct.",
        )

    login_limiter.reset(limiter_key)
    login_user(page.request, user)
    logger.info("User %s logged in", user.itid)
    return redirect("/services")


@router.get("/login")
def login_form(page: Page = Depends(), uHash: str = None, pHash: str = None):
    """Shows the login form. The link in the registration e-mail logs in directly."""

    if uHash and pHash:
        return _login(page, uHash, pHash, _login_key(page.request, uHash))
    if page.user is not None:
        return redirect("/services")
    return page.render("login.html", email="", error=None)


@router.post("/login", dependencies=[Depends(csrf_protect)])
def login(page: Page = Depends(), email: str = Form(""), pin: str = Form("")):
    email = email.strip().lower()
    return _login(
        page,
        email_hash(email),
        pin_hash(pin.strip()),
        _login_key(page.request, email),
        email=email,
    )


@router.post("/logout", dependencies=[Depends(csrf_protect)])
def logout(request: Request):
    logout_user(request)
    flash(request, "You are logged out.", "success")
    return redirect("/login")
