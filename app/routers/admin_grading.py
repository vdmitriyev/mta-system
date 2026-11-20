"""Admin pages Reviews and Bonus points: grading of the users"""

from fastapi import APIRouter, Depends, Form, HTTPException

from app import submissions
from app.admin_log import log_action
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
from app.models import ExerciseBonusPoints, ExerciseReviews
from app.routers.admin import get_course_user, user_rows
from app.security import csrf_protect
from app.users import course_users, email_to_name, neighbours
from app.web import Page, flash, redirect, require_admin

router = APIRouter(
    prefix="/mtas-admin", include_in_schema=False, dependencies=[Depends(require_admin)]
)


@router.get("/reviews")
def reviews_page(page: Page = Depends(), todo: bool = False):
    """todo: only the users with files that are not reviewed yet"""

    exercises = get_exercises(page.db, part=PART_REVIEW)
    with_files = submissions.users_with_files(
        page.db, [exercise.itid for exercise in exercises if exercise.has_submission]
    )
    rows = user_rows(page.db)
    for row in rows:
        row["reviews"] = get_user_reviews(page.db, exercises, row["user"].itid)
        for exercise, item in zip(exercises, row["reviews"]):
            item["to_review"] = (
                row["user"].itid,
                exercise.itid,
            ) in with_files and not item["reviewed"]
        row["to_review"] = sum(item["to_review"] for item in row["reviews"])
    open_reviews = sum(row["to_review"] for row in rows)
    if todo:
        rows = [row for row in rows if row["to_review"]]
    return page.render(
        "admin/reviews.html",
        rows=rows,
        exercises=exercises,
        todo=todo,
        open_reviews=open_reviews,
    )


def review_neighbours(page: Page, exercise, user_id: int) -> dict:
    """Previous and next user in the order of the table Reviews.

    Exercise with submissions: only the users with files.
    """

    order = [user.itid for user in course_users(page.db)]
    included = None
    if exercise.has_submission:
        included = {
            itid for itid, _ in submissions.users_with_files(page.db, [exercise.itid])
        }
    result = neighbours(order, user_id, included)
    for key in ("previous", "next"):
        if result[key] is not None:
            result[key] = (
                f"/mtas-admin/reviews/edit?user={result[key]}&exercise={exercise.code}"
            )
    return result


def _review_edit(page: Page, user_id, exercise_code: str):
    exercise = get_exercise(page.db, exercise_code)
    if exercise is None:
        raise HTTPException(status_code=404)
    student = get_course_user(page.db, user_id)
    review = get_latest_review(page.db, student.itid, exercise.itid)
    files = (
        submissions.active_submissions(page.db, student.itid, exercise.itid)
        if exercise.has_submission
        else []
    )
    if review is not None:
        submitted = review.submitted
    elif exercise.has_submission:
        submitted = bool(files)
    else:
        submitted = True
    return page.render(
        "admin/review_edit.html",
        student=student,
        student_name=email_to_name(student.email),
        exercise=exercise,
        review=review,
        preview=render_review_content(review) if review else None,
        submitted=submitted,
        files=files,
        neighbours=review_neighbours(page, exercise, student.itid),
        format_size=submissions.format_size,
        bonus=(
            get_latest_bonus_points(page.db, student.itid, exercise.itid)
            if exercise.has_bonus
            else None
        ),
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
    log_action(
        page.db,
        page.user,
        "review",
        student.itid,
        exercise_db.code,
        f"submitted={submitted}, reviewed={reviewed}, visible={visible}",
    )
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


def bonus_points_error(points: str, max_points: float | None) -> str | None:
    try:
        value = float(points.replace(",", "."))
    except ValueError:
        return "Enter the bonus points as a number."
    if value != value or value < 0:
        return "Enter the bonus points as a number of 0 or more."
    if max_points is not None and value > max_points:
        return f"The bonus points can be at most {max_points:g}."
    return None


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
    back: str = Form(""),
):
    exercise_db = get_exercise(page.db, exercise)
    if exercise_db is None:
        raise HTTPException(status_code=404)
    student = get_course_user(page.db, user)
    # the form is also on the page of the review
    page_url = "reviews" if back == "review" else "bonus"
    target = f"/mtas-admin/{page_url}/edit?user={student.itid}&exercise={exercise}"

    error = bonus_points_error(points, exercise_db.bonus_max_points)
    if error:
        if back == "review":
            flash(page.request, error, "danger")
            return redirect(target)
        return _bonus_edit(page, user, exercise, status_code=400, error=error)
    value = float(points.replace(",", "."))

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
    log_action(
        page.db,
        page.user,
        "bonus",
        student.itid,
        exercise_db.code,
        f"points={value:g}, visible={visible}, counts={is_addable}",
    )
    flash(page.request, "The bonus points were saved.", "success")
    return redirect(target)
