"""Shared parts of the HTML pages: templates, login state, messages"""

from functools import cached_property

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import __version__
from app.config import BASE_DIR, get_settings
from app.database import get_db
from app.models import Users
from app.security import csrf_token
from app.users import find_user_by_hash, is_admin
from app.visibility import ui_visibility_settings

SESSION_USER_KEY = "user"
SESSION_FLASH_KEY = "flashes"
FLASH_LEVELS = ("info", "success", "warning", "danger")

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


class NotAuthenticated(Exception):
    """The page needs a login"""


def flash(request: Request, message: str, level: str = "info") -> None:
    """Stores a message that the next page shows once"""

    if level not in FLASH_LEVELS:
        level = "info"
    messages = request.session.get(SESSION_FLASH_KEY, [])
    messages.append({"level": level, "text": message})
    request.session[SESSION_FLASH_KEY] = messages


def redirect(url: str) -> RedirectResponse:
    """Redirect after a form was handled (the browser then loads the page with GET)"""

    return RedirectResponse(url, status_code=303)


def login_user(request: Request, user: Users) -> None:
    # new session: nothing of an earlier visitor is kept
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.url_hash


def logout_user(request: Request) -> None:
    request.session.clear()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Users | None:
    user = find_user_by_hash(db, request.session.get(SESSION_USER_KEY))
    if user is not None and not user.active:
        return None
    return user


def require_user(user: Users | None = Depends(get_current_user)) -> Users:
    if user is None:
        raise NotAuthenticated()
    return user


def require_admin(user: Users = Depends(require_user)) -> Users:
    if not is_admin(user):
        raise HTTPException(status_code=403)
    return user


class Page:
    """Renders a template with the values that every page needs"""

    def __init__(
        self,
        request: Request,
        db: Session = Depends(get_db),
        user: Users | None = Depends(get_current_user),
    ):
        self.request = request
        self.db = db
        self.user = user

    @cached_property
    def visibility(self) -> dict:
        return ui_visibility_settings(self.db)

    def render(self, template: str, status_code: int = 200, **context):
        settings = get_settings()
        context.update(
            course_name=settings.course_name_title,
            visibility=self.visibility,
            user=self.user,
            is_admin=is_admin(self.user),
            flashes=self.request.session.pop(SESSION_FLASH_KEY, []),
            csrf_token=csrf_token(self.request),
            api_docs=settings.enable_api_docs,
            app_version=__version__,
            path=self.request.url.path,
        )
        return templates.TemplateResponse(
            self.request, template, context, status_code=status_code
        )
