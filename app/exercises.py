import markdown
from markupsafe import Markup
from sqlalchemy.orm import Session

from app.models import ExerciseBonusPoints, ExerciseReviews, Exercises

PART_REVIEW = "review"
PART_BONUS = "bonus"


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
    """Gets the review state of a user for each of the given exercises"""

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
        }
        entry = get_latest_bonus_points(db, user_id, exercise.itid)
        if entry is not None:
            item.update(
                points=entry.points, visible=entry.visible, is_addable=entry.is_addable
            )
            if entry.is_addable:
                bonus_total += entry.points
        bonus_points.append(item)

    return bonus_points, bonus_total
