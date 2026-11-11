"""Admin pages of PostgreSQL and pgAdmin 4: the accounts of the users and checks"""

import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Form

from app import config, provisioning
from app.config import get_settings
from app.models import PostgreSQLService
from app.routers.admin import (
    account_number,
    check_basic_auth,
    get_course_user,
    user_rows,
)
from app.security import csrf_protect, random_string
from app.services import basic_auth, postgresql
from app.tasks import TaskError
from app.users import get_user_services
from app.web import Page, flash, redirect, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/mtas-admin/services",
    include_in_schema=False,
    dependencies=[Depends(require_admin)],
)


def _rows(page: Page, service: str) -> list:
    rows = user_rows(page.db)
    for row in rows:
        services = get_user_services(page.db, row["user"].itid)
        row["entry"] = services.get(service)
        row["postgresql"] = services.get("postgresql")
    return rows


def _number(user) -> str:
    """Number of the account with two digits, as in the names of the services"""

    try:
        return str(account_number(user)).zfill(2)
    except TaskError as error:
        raise postgresql.PostgreSQLError(str(error)) from error


# ---------- PostgreSQL ----------


@router.get("/postgresql")
def postgresql_page(page: Page = Depends(), check: str | None = None):
    """Databases of the users. ?check=access logs in as each user."""

    rows = _rows(page, "postgresql")
    server = postgresql.server_status()
    databases = postgresql.existing_databases() if server.ok else None
    for row in rows:
        entry = row["entry"]
        if entry is None or databases is None:
            row["database"] = None
        else:
            row["database"] = entry.postgresql_db in databases

    access_checked = check == "access"
    if access_checked:
        jobs = [row for row in rows if row["entry"] is not None]
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = executor.map(
                lambda row: postgresql.check_user_access(
                    row["entry"].postgresql_db,
                    row["entry"].postgresql_user,
                    row["entry"].postgresql_password,
                ),
                jobs,
            )
            for row, result in zip(jobs, results):
                row["access"] = result
        for row in rows:
            row.setdefault("access", "NO SERVICE")

    return page.render(
        "admin/postgresql.html",
        rows=rows,
        server=server,
        demo_db=get_settings().postgresql_demo_db,
        demo_exists=(
            postgresql.database_exists(get_settings().postgresql_demo_db)
            if server.ok
            else None
        ),
        access_checked=access_checked,
    )


def create_postgresql_account(db, user) -> str:
    """Creates the database of a user. Uses the stored names and password, if there are some."""

    entry = get_user_services(db, user.itid).get("postgresql")
    databases = postgresql.existing_databases()
    if databases is None:
        raise postgresql.PostgreSQLError("The PostgreSQL server is not reachable.")

    if entry is not None:
        if entry.postgresql_db in databases:
            raise postgresql.PostgreSQLError(
                f"The database {entry.postgresql_db} already exists. "
                "If the user cannot log in, use “Set password”."
            )
        postgresql.create_database(
            entry.postgresql_db, entry.postgresql_user, entry.postgresql_password
        )
        entry.created = True
        db.commit()
        return f"The database {entry.postgresql_db} was created again for {user.email}."

    number = _number(user)
    db_name = f"{config.POSTGRESQL_DB_PREFIX}_{number}"
    db_user = f"{config.POSTGRESQL_USER_PREFIX}_{number}"
    password = random_string()
    postgresql.create_database(db_name, db_user, password)
    db.add(
        PostgreSQLService(
            user_id=user.itid,
            postgresql_db=db_name,
            postgresql_user=db_user,
            postgresql_password=password,
            created=True,
        )
    )
    db.commit()
    return f"The database {db_name} was created for {user.email}."


@router.post("/postgresql/create", dependencies=[Depends(csrf_protect)])
def postgresql_create(page: Page = Depends(), user_id: int = Form(...)):
    student = get_course_user(page.db, user_id)
    try:
        flash(page.request, create_postgresql_account(page.db, student), "success")
    except postgresql.PostgreSQLError as error:
        flash(page.request, f"Not created: {error}", "danger")
    return redirect("/mtas-admin/services/postgresql")


@router.post("/postgresql/password", dependencies=[Depends(csrf_protect)])
def postgresql_password(page: Page = Depends(), user_id: int = Form(...)):
    """Sets the password in PostgreSQL to the one that the user sees on the services page"""

    student = get_course_user(page.db, user_id)
    entry = get_user_services(page.db, student.itid).get("postgresql")
    if entry is None:
        flash(page.request, f"{student.email} has no PostgreSQL account.", "danger")
        return redirect("/mtas-admin/services/postgresql")
    try:
        postgresql.set_password(entry.postgresql_user, entry.postgresql_password)
        flash(
            page.request,
            f"The password of {entry.postgresql_user} in PostgreSQL is now the one "
            f"on the services page of {student.email}.",
            "success",
        )
    except postgresql.PostgreSQLError as error:
        flash(page.request, f"Password not set: {error}", "danger")
    return redirect("/mtas-admin/services/postgresql")


# ---------- pgAdmin 4 ----------


@router.get("/pgadmin4")
def pgadmin4_page(page: Page = Depends(), check: str | None = None):
    """pgAdmin 4 logins of the users (nginx basic auth). ?check=access requests pgAdmin 4."""

    settings = get_settings()
    auth_file = basic_auth.common_auth_file()
    rows = _rows(page, "pgadmin4")
    for row in rows:
        entry = row["entry"]
        row["login_state"] = (
            basic_auth.login_state(
                entry.pgadmin4_user, entry.pgadmin4_password, auth_file
            )
            if entry
            else None
        )

    access_checked = check == "access"
    if access_checked:
        jobs = [row for row in rows if row["entry"] is not None]
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = executor.map(
                lambda row: check_basic_auth(
                    settings.pgadmin4_url,
                    row["entry"].pgadmin4_user,
                    row["entry"].pgadmin4_password,
                ),
                jobs,
            )
            for row, result in zip(jobs, results):
                row["access"] = result
        for row in rows:
            row.setdefault("access", "NO SERVICE")

    return page.render(
        "admin/pgadmin4.html",
        rows=rows,
        auth_file=auth_file,
        login_count=basic_auth.count_logins(auth_file),
        pgadmin4_url=settings.pgadmin4_url,
        access_checked=access_checked,
    )


@router.post("/pgadmin4/login", dependencies=[Depends(csrf_protect)])
def pgadmin4_login(page: Page = Depends(), user_id: int = Form(...)):
    """Writes the login of a user into the login file. Creates the account, if there is none."""

    student = get_course_user(page.db, user_id)
    services = get_user_services(page.db, student.itid)
    entry = services.get("pgadmin4")
    if entry is not None:
        basic_auth.set_basic_auth_user(
            entry.pgadmin4_user, entry.pgadmin4_password, basic_auth.common_auth_file()
        )
        entry.created = True
        page.db.commit()
        flash(
            page.request,
            f"The pgAdmin 4 login of {student.email} was written.",
            "success",
        )
        return redirect("/mtas-admin/services/pgadmin4")

    try:
        number = _number(student)
    except postgresql.PostgreSQLError as error:
        flash(page.request, f"Not created: {error}", "danger")
        return redirect("/mtas-admin/services/pgadmin4")
    # the same password as for PostgreSQL, as at the registration
    password = (
        services["postgresql"].postgresql_password
        if "postgresql" in services
        else random_string()
    )
    provisioning.pgadmin4_user(
        page.db,
        student.itid,
        f"{config.PGADMIN4_USER_PREFIX}_{number}",
        password,
        force_create=True,
    )
    flash(page.request, f"pgAdmin 4 was set up for {student.email}.", "success")
    return redirect("/mtas-admin/services/pgadmin4")
