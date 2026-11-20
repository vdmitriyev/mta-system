import csv
import io
from datetime import datetime

import markdown
from markupsafe import Markup
from sqlalchemy.orm import Session

from app.models import (
    ExerciseBonusPoints,
    ExerciseReviews,
    Exercises,
    ExerciseSubmissions,
)
from app.timeutil import to_local

PART_REVIEW = "review"
PART_BONUS = "bonus"

# Columns of setup/initial_exercises.csv (import and export), separated by ";"
EXERCISE_COLUMNS = (
    "code",
    "name",
    "description",
    "year",
    "visible",
    "exercise_order",
    "submission_deadline",
    "has_review",
    "has_bonus",
    "bonus_max_points",
    "has_submission",
    "submission_email",
)
CSV_DELIMITER = ";"


def get_exercises(db: Session, part: str = None, only_visible: bool = False) -> list:
    """Gets the exercises, ordered by exercise_order

    Args:
        part (str, optional): PART_REVIEW or PART_BONUS to get only exercises with this part
        only_visible (bool, optional): get only visible exercises
    """

    query = db.query(Exercises)
    if part == PART_REVIEW:
        query = query.filter(Exercises.has_review.is_(True))
    if part == PART_BONUS:
        query = query.filter(Exercises.has_bonus.is_(True))
    if only_visible:
        query = query.filter(Exercises.visible.is_(True))
    return query.order_by(Exercises.exercise_order.asc()).all()


def get_exercise(db: Session, code: str) -> Exercises | None:
    return db.query(Exercises).filter(Exercises.code == code).first()


def get_latest_review(
    db: Session, user_id: int, exercise_id: int
) -> ExerciseReviews | None:
    """Gets the newest review of a user for an exercise"""

    return (
        db.query(ExerciseReviews)
        .filter(
            ExerciseReviews.user_id == user_id,
            ExerciseReviews.exercise_id == exercise_id,
        )
        .order_by(ExerciseReviews.created_at.desc(), ExerciseReviews.itid.desc())
        .first()
    )


def get_latest_bonus_points(
    db: Session, user_id: int, exercise_id: int
) -> ExerciseBonusPoints | None:
    """Gets the newest bonus points of a user for an exercise"""

    return (
        db.query(ExerciseBonusPoints)
        .filter(
            ExerciseBonusPoints.user_id == user_id,
            ExerciseBonusPoints.exercise_id == exercise_id,
            ExerciseBonusPoints.deleted.is_(False),
        )
        .order_by(
            ExerciseBonusPoints.created_at.desc(), ExerciseBonusPoints.itid.desc()
        )
        .first()
    )


def render_review_content(review: ExerciseReviews):
    """Returns the review content ready for a template (Markdown as HTML)"""

    if review.render_format == "MARKDOWN":
        # only admins write reviews; they can use HTML in the Markdown text
        return Markup(markdown.markdown(review.content or ""))  # nosec B704
    return review.content


def get_user_reviews(db: Session, exercises: list, user_id: int) -> list:
    """Gets the review state of a user for each of the given exercises.

    An exercise with submissions counts as submitted while the user has files
    for it that are not deleted; the saved review does not change that.
    """

    with_files = {
        exercise_id
        for (exercise_id,) in db.query(ExerciseSubmissions.exercise_id)
        .filter(
            ExerciseSubmissions.user_id == user_id,
            ExerciseSubmissions.deleted.is_(False),
        )
        .distinct()
    }
    reviews = []
    for exercise in exercises:
        item = {
            "code": exercise.code,
            "name": exercise.name,
            "has_content": False,
            "submitted": False,
            "reviewed": False,
            "visible": False,
            "content": None,
        }
        review = get_latest_review(db, user_id, exercise.itid)
        if review is not None:
            item.update(
                has_content=bool(review.content),
                submitted=review.submitted,
                reviewed=review.reviewed,
                visible=review.visible,
                content=render_review_content(review),
            )
        if exercise.has_submission:
            item["submitted"] = exercise.itid in with_files
        reviews.append(item)
    return reviews


def get_user_bonus_points(db: Session, exercises: list, user_id: int) -> tuple:
    """Gets the bonus points of a user for the given exercises

    Returns:
        tuple: list with the bonus points per exercise, total of the bonus points
    """

    bonus_points = []
    bonus_total = 0.0
    for exercise in exercises:
        item = {
            "code": exercise.code,
            "name": exercise.name,
            "max_points": exercise.bonus_max_points,
            "points": 0.0,
            "visible": False,
            "is_addable": False,
            "is_set": False,
        }
        entry = get_latest_bonus_points(db, user_id, exercise.itid)
        if entry is not None:
            item.update(
                points=entry.points,
                visible=entry.visible,
                is_addable=entry.is_addable,
                is_set=True,
            )
            if entry.is_addable:
                bonus_total += entry.points
        bonus_points.append(item)

    return bonus_points, bonus_total


def _csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        # the CSV file is written by people: local time
        return to_local(value).isoformat()
    return str(value)


def exercise_csv_row(exercise: Exercises) -> dict:
    """The exercise as a row of the CSV file, in the format of the import"""

    return {
        column: _csv_value(getattr(exercise, column)) for column in EXERCISE_COLUMNS
    }


def exercises_csv(db: Session) -> str:
    """All exercises (also the hidden ones) as CSV, ready for the import"""

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=EXERCISE_COLUMNS,
        delimiter=CSV_DELIMITER,
        lineterminator="\n",
    )
    writer.writeheader()
    for exercise in get_exercises(db):
        writer.writerow(exercise_csv_row(exercise))
    return output.getvalue()
