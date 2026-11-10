from markupsafe import Markup

from ..extensions import db
from ..models import ExerciseBonusPoints, ExerciseReviews, Exercises
from ..utils.uhelpers import to_json_sqla

PART_REVIEW = "review"
PART_BONUS = "bonus"


def get_exercises(part: str = None, only_visible: bool = False) -> dict:
    """Gets the exercises, ordered by exercise_order

    Args:
        part (str, optional): PART_REVIEW or PART_BONUS to get only exercises with this part
        only_visible (bool, optional): get only visible exercises

    Returns:
        dict: exercise code -> exercise as dict
    """

    query = db.session.query(Exercises)
    if part == PART_REVIEW:
        query = query.filter(Exercises.has_review == True)
    if part == PART_BONUS:
        query = query.filter(Exercises.has_bonus == True)
    if only_visible:
        query = query.filter(Exercises.visible == True)

    exercises = {}
    for item in query.order_by(Exercises.exercise_order.asc()).all():
        exercises[item.code] = to_json_sqla(item)
    return exercises


def get_exercise(code: str) -> Exercises:
    """Gets an exercise by its code (None if there is no such exercise)"""

    return db.session.query(Exercises).filter(Exercises.code == code).first()


def get_latest_review(user_id: int, exercise_id: int) -> ExerciseReviews:
    """Gets the newest review of a user for an exercise (None if there is none)"""

    return (
        db.session.query(ExerciseReviews)
        .filter(
            ExerciseReviews.user_id == user_id,
            ExerciseReviews.exercise_id == exercise_id,
        )
        .order_by(ExerciseReviews.created_at.desc(), ExerciseReviews.itid.desc())
        .first()
    )


def get_latest_bonus_points(user_id: int, exercise_id: int) -> ExerciseBonusPoints:
    """Gets the newest bonus points of a user for an exercise (None if there are none)"""

    return (
        db.session.query(ExerciseBonusPoints)
        .filter(
            ExerciseBonusPoints.user_id == user_id,
            ExerciseBonusPoints.exercise_id == exercise_id,
            ExerciseBonusPoints.deleted == False,
        )
        .order_by(
            ExerciseBonusPoints.created_at.desc(), ExerciseBonusPoints.itid.desc()
        )
        .first()
    )


def render_review_content(review: dict):
    """Returns the review content ready for a template (Markdown as HTML)"""

    if review["render_format"] == "MARKDOWN":
        import markdown

        return Markup(markdown.markdown(review["content"] or ""))
    return review["content"]


def get_user_bonus_points(exercises: dict, user_id: int) -> tuple:
    """Gets the bonus points of a user for the given exercises

    Args:
        exercises (dict): exercises with a bonus part (see get_exercises)
        user_id (int): user id

    Returns:
        tuple: list with the bonus points per exercise, total of the bonus points
    """

    bonus_points = []
    bonus_total = 0.0
    for exercise in exercises.values():
        item = {
            "code": exercise["code"],
            "name": exercise["name"],
            "max_points": exercise["bonus_max_points"],
            "points": 0.0,
            "visible": False,
            "is_addable": False,
        }
        entry = get_latest_bonus_points(user_id, exercise["itid"])
        if entry is not None:
            item["points"] = entry.points
            item["visible"] = entry.visible
            item["is_addable"] = entry.is_addable
            if entry.is_addable:
                bonus_total += entry.points
        bonus_points.append(item)

    return bonus_points, bonus_total
