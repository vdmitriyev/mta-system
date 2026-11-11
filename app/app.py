import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.config import BASE_DIR, Settings, get_settings, set_settings
from app.database import init_engine, session_scope
from app.routers import account, admin, api, public
from app.service_settings import add_default_service_settings
from app.tasks import fail_stale_tasks
from app.visibility import add_default_ui_visibility_settings
from app.web import NotAuthenticated, Page, get_current_user, redirect

logger = logging.getLogger(__name__)

ERROR_PAGES = {
    400: ("Bad request", "The request is not complete or not valid."),
    401: ("Login needed", "Log in to see this page."),
    403: ("No access", "You have no rights to see this page."),
    404: ("Page not found", "This page does not exist. Check the address."),
    405: ("Not allowed", "This action is not allowed here."),
    500: ("Server error", "Something went wrong on the server. Try again later."),
}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}
# All styles and scripts of the pages are files of the app
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
# Swagger UI and ReDoc load their files from a CDN
DOCS_PATHS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(SECURITY_HEADERS)
                if not scope["path"].startswith(DOCS_PATHS):
                    headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
                message["headers"] = list(message.get("headers", [])) + [
                    (name.lower().encode(), value.encode())
                    for name, value in headers.items()
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def error_response(request: Request, status_code: int, detail: str = None):
    title, default_detail = ERROR_PAGES.get(status_code, ("Error", "Request failed."))
    if wants_json(request):
        return JSONResponse(
            {"error": title.lower(), "detail": detail or default_detail},
            status_code=status_code,
        )
    with session_scope() as db:
        page = Page(request, db, get_current_user(request, db))
        return page.render(
            "error.html",
            status_code=status_code,
            title=title,
            detail=detail or default_detail,
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with session_scope() as db:
        add_default_ui_visibility_settings(db)
        add_default_service_settings(db)
        try:
            fail_stale_tasks(db)
        except Exception:
            # the table is missing until the migrations ran
            logger.warning("Background tasks were not checked: run the migrations")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Creates the FastAPI app. Without settings, they are read from the environment."""

    if settings is not None:
        set_settings(settings)
    settings = get_settings()
    init_engine(settings.database_url)

    docs = settings.enable_api_docs
    app = FastAPI(
        title="mta-system",
        description="Modular teaching assistance system",
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="mtas_session",
        max_age=settings.session_max_age_days * 24 * 60 * 60,
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )

    app.mount(
        "/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static"
    )
    for router in (public.router, account.router, admin.router, api.router):
        app.include_router(router)

    @app.exception_handler(NotAuthenticated)
    async def not_authenticated(request: Request, _exc: NotAuthenticated):
        if wants_json(request):
            return error_response(request, 401)
        return redirect("/login")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        # FastAPI sets the name of the status as the default detail: use our text
        default = exc.detail in (None, "") or exc.status_code not in (400, 403)
        return error_response(
            request, exc.status_code, None if default else str(exc.detail)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError):
        return error_response(request, 400)

    @app.exception_handler(Exception)
    async def server_error(request: Request, _exc: Exception):
        logger.exception("Unhandled error: %s %s", request.method, request.url.path)
        return error_response(request, 500)

    return app
