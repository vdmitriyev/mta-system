"""Admin pages: exercises (deadlines) and the files that the users submitted"""

import os
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from app import submissions
from app.admin_log import log_action
from app.exercises import exercises_csv, get_exercise, get_exercises
from app.models import Exercises, Users
from app.routers.submissions import file_response
from app.security import csrf_protect
from app.users import course_users, email_to_name, neighbours
from app.web import Page, flash, redirect, require_admin

CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")

router = APIRouter(
    prefix="/mtas-admin", include_in_schema=False, dependencies=[Depends(require_admin)]
)


DEADLINE_FORMAT = "%d.%m.%Y %H:%M"


def parse_deadline(value: str) -> datetime | None:
    """30.11.2026 23:59, 30.11.2026 (until 23:59) or ISO 2026-11-30T23:59. Empty: None."""

    value = " ".join((value or "").split())
    if not value:
        return None
    for fmt, end_of_day in ((DEADLINE_FORMAT, False), ("%d.%m.%Y", True)):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed.replace(hour=23, minute=59) if end_of_day else parsed
    return datetime.fromisoformat(value).replace(second=0, microsecond=0)


def deadline_input(value: datetime | None) -> str:
    return value.strftime(DEADLINE_FORMAT) if value else ""


def exercise_or_404(page: Page, code: str) -> Exercises:
    exercise = get_exercise(page.db, code)
    if exercise is None:
        raise HTTPException(status_code=404)
    return exercise


def student_or_404(page: Page, user_id: int) -> Users:
    student = page.db.query(Users).filter(Users.itid == user_id).first()
    if student is None:
        raise HTTPException(status_code=404)
    return student


# ---- exercises ----


@router.get("/exercises")
def exercises_page(page: Page = Depends()):
    return page.render("admin/exercises.html", exercises=get_exercises(page.db))


@router.get("/exercises/export")
def exercises_export(page: Page = Depends()):
    """All exercises as CSV: a backup, and setup/initial_exercises.csv of a new deployment"""

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        exercises_csv(page.db),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="initial_exercises-{stamp}.csv"'
        },
    )


def _exercise_form(
    page: Page, exercise: Exercises | None, status_code=200, error=None, values=None
):
    return page.render(
        "admin/exercise_edit.html",
        status_code=status_code,
        exercise=exercise,
        values=values or exercise_values(exercise),
        error=error,
    )


def exercise_values(exercise: Exercises | None) -> dict:
    """Values of the form"""

    if exercise is None:
        return {
            "code": "",
            "name": "",
            "description": "",
            "year": str(datetime.now().year),
            "exercise_order": "",
            "submission_deadline": "",
            "bonus_max_points": "",
            "visible": True,
            "has_review": True,
            "has_bonus": False,
            "has_submission": False,
            "submission_email": False,
        }
    return {
        "code": exercise.code,
        "name": exercise.name or "",
        "description": exercise.description or "",
        "year": "" if exercise.year is None else str(exercise.year),
        "exercise_order": (
            "" if exercise.exercise_order is None else str(exercise.exercise_order)
        ),
        "submission_deadline": deadline_input(exercise.submission_deadline),
        "bonus_max_points": (
            "" if exercise.bonus_max_points is None else str(exercise.bonus_max_points)
        ),
        "visible": exercise.visible,
        "has_review": exercise.has_review,
        "has_bonus": exercise.has_bonus,
        "has_submission": exercise.has_submission,
        "submission_email": exercise.submission_email,
    }


@router.get("/exercises/edit")
def exercise_edit_form(page: Page = Depends(), code: str | None = None):
    exercise = exercise_or_404(page, code) if code else None
    return _exercise_form(page, exercise)


@router.post("/exercises/edit", dependencies=[Depends(csrf_protect)])
def exercise_save(
    page: Page = Depends(),
    original_code: str = Form(""),
    code: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    year: str = Form(""),
    exercise_order: str = Form(""),
    submission_deadline: str = Form(""),
    bonus_max_points: str = Form(""),
    visible: bool = Form(False),
    has_review: bool = Form(False),
    has_bonus: bool = Form(False),
    has_submission: bool = Form(False),
    submission_email: bool = Form(False),
):
    exercise = exercise_or_404(page, original_code) if original_code else None
    values = {
        "code": exercise.code if exercise else code.strip(),
        "name": name.strip(),
        "description": description.strip(),
        "year": year.strip(),
        "exercise_order": exercise_order.strip(),
        "submission_deadline": submission_deadline.strip(),
        "bonus_max_points": bonus_max_points.strip(),
        "visible": visible,
        "has_review": has_review,
        "has_bonus": has_bonus,
        "has_submission": has_submission,
        "submission_email": submission_email,
    }

    def invalid(message: str):
        return _exercise_form(page, exercise, 400, message, values)

    if exercise is None:
        if not CODE_PATTERN.match(values["code"]):
            return invalid(
                "Enter a code of 1 to 20 letters, digits, '_' or '-', e.g. EX01."
            )
        if get_exercise(page.db, values["code"]):
            return invalid(f"The code {values['code']} already exists.")
    if not values["name"]:
        return invalid("Enter a name.")
    try:
        parsed = {
            "year": int(values["year"]) if values["year"] else None,
            "exercise_order": (
                int(values["exercise_order"]) if values["exercise_order"] else None
            ),
            "bonus_max_points": (
                float(values["bonus_max_points"].replace(",", "."))
                if values["bonus_max_points"]
                else None
            ),
        }
    except ValueError:
        return invalid("Enter the year, the order and the bonus points as numbers.")
    try:
        parsed["submission_deadline"] = parse_deadline(values["submission_deadline"])
    except ValueError:
        return invalid("Enter the deadline as date and time.")

    if exercise is None:
        exercise = Exercises(code=values["code"])
        page.db.add(exercise)
    exercise.name = values["name"]
    exercise.description = values["description"] or None
    for key in ("visible", "has_review", "has_bonus", "has_submission"):
        setattr(exercise, key, values[key])
    exercise.submission_email = values["submission_email"]
    for key, value in parsed.items():
        setattr(exercise, key, value)
    page.db.commit()
    log_action(page.db, page.user, "exercise", exercise_code=exercise.code)
    flash(page.request, f"Exercise {exercise.code} was saved.", "success")
    return redirect("/mtas-admin/exercises")


# ---- submissions ----


@router.get("/submissions")
def submissions_page(page: Page = Depends()):
    exercises = submissions.submission_exercises(page.db, only_visible=False)
    users = course_users(page.db)
    cells = submissions.submission_matrix(
        page.db, exercises, [user.itid for user in users]
    )
    rows = [
        {
            "user": user,
            "name": email_to_name(user.email),
            "cells": [cells.get((user.itid, exercise.itid)) for exercise in exercises],
        }
        for user in users
    ]
    totals = [
        sum(1 for row in rows if row["cells"][index] and row["cells"][index]["count"])
        for index in range(len(exercises))
    ]
    return page.render(
        "admin/submissions.html",
        exercises=exercises,
        rows=rows,
        totals=totals,
        folder=str(submissions.root_dir()),
        storage=submissions.storage_summary(page.db, exercises),
        format_size=submissions.format_size,
    )


def _detail_url(user_id: int, code: str) -> str:
    return f"/mtas-admin/submissions/detail?user={user_id}&exercise={code}"


def submission_neighbours(page: Page, exercise: Exercises, user_id: int) -> dict:
    """Previous and next user with files for the exercise, in the order of the table"""

    with_files = {
        itid for itid, _ in submissions.users_with_files(page.db, [exercise.itid])
    }
    order = [user.itid for user in course_users(page.db)]
    result = neighbours(order, user_id, with_files)
    for key in ("previous", "next"):
        if result[key] is not None:
            result[key] = _detail_url(result[key], exercise.code)
    return result


@router.get("/submissions/detail")
def submission_detail(user: int, exercise: str, page: Page = Depends()):
    exercise_db = exercise_or_404(page, exercise)
    student = student_or_404(page, user)
    deadline = submissions.effective_deadline(page.db, exercise_db, student.itid)
    extension = submissions.get_extension(page.db, exercise_db.itid, student.itid)
    files = submissions.all_submissions(page.db, student.itid, exercise_db.itid)
    return page.render(
        "admin/submission_detail.html",
        student=student,
        student_name=email_to_name(student.email),
        exercise=exercise_db,
        files=files,
        neighbours=submission_neighbours(page, exercise_db, student.itid),
        same_files=submissions.same_files(page.db, files),
        deadline=deadline,
        is_open=submissions.is_open(deadline),
        extension=extension,
        extension_input=deadline_input(extension.deadline if extension else None),
        format_size=submissions.format_size,
    )


@router.post("/submissions/extension", dependencies=[Depends(csrf_protect)])
def submission_extension(
    page: Page = Depends(),
    user: int = Form(...),
    exercise: str = Form(...),
    deadline: str = Form(""),
    note: str = Form(""),
    remove: bool = Form(False),
):
    exercise_db = exercise_or_404(page, exercise)
    student = student_or_404(page, user)
    if remove:
        if submissions.remove_extension(page.db, exercise_db, student.itid):
            log_action(
                page.db, page.user, "extension_removed", student.itid, exercise_db.code
            )
            flash(page.request, "The extension was removed.", "success")
        return redirect(_detail_url(student.itid, exercise_db.code))
    try:
        parsed = parse_deadline(deadline)
    except ValueError:
        parsed = None
    if parsed is None:
        flash(page.request, "Enter the new deadline as date and time.", "danger")
        return redirect(_detail_url(student.itid, exercise_db.code))
    submissions.set_extension(page.db, exercise_db, student.itid, parsed, note)
    log_action(
        page.db,
        page.user,
        "extension",
        student.itid,
        exercise_db.code,
        f"{parsed:%d.%m.%Y %H:%M}" + (f", {note.strip()}" if note.strip() else ""),
    )
    flash(
        page.request,
        f"New deadline for {student.email}: {parsed:%d.%m.%Y %H:%M}.",
        "success",
    )
    return redirect(_detail_url(student.itid, exercise_db.code))


@router.post("/submissions/delete", dependencies=[Depends(csrf_protect)])
def submission_delete(page: Page = Depends(), submission_id: int = Form(...)):
    row = submissions.get_submission(page.db, submission_id)
    if row is None or row.deleted:
        raise HTTPException(status_code=404)
    exercise = page.db.get(Exercises, row.exercise_id)
    try:
        submissions.delete_submission(page.db, row)
        log_action(
            page.db,
            page.user,
            "file_deleted",
            row.user_id,
            exercise.code,
            f"{row.original_name} (SHA-256 {row.sha256[:12]})",
        )
        flash(page.request, f"Deleted: {row.original_name}", "success")
    except submissions.SubmissionError as error:
        flash(page.request, str(error), "danger")
    return redirect(_detail_url(row.user_id, exercise.code))


@router.get("/submissions/file/{submission_id}")
def submission_file(submission_id: int, page: Page = Depends(), inline: bool = False):
    row = submissions.get_submission(page.db, submission_id)
    if row is None or row.deleted:
        raise HTTPException(status_code=404)
    return file_response(row, inline=inline)


@router.get("/submissions/zip/{code}")
def submission_zip(code: str, page: Page = Depends()):
    exercise = exercise_or_404(page, code)
    path, count = submissions.zip_exercise(page.db, exercise)
    if count == 0:
        os.unlink(path)
        flash(page.request, f"There are no files for {exercise.code}.", "info")
        return redirect("/mtas-admin/submissions")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"submissions-{submissions.exercise_folder_name(exercise)}-{stamp}.zip",
        background=BackgroundTask(os.unlink, path),
    )
