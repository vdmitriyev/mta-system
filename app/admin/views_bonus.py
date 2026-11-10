from flask import abort, current_app, render_template, request
from flask_login import login_required

from ..extensions import db
from ..main.exercises_helpers import (
    PART_BONUS,
    get_exercise,
    get_exercises,
    get_latest_bonus_points,
    get_user_bonus_points,
)
from ..main.mhelpers import email_to_name
from ..models import ExerciseBonusPoints, Users
from ..utils.uhelpers import to_json_sqla
from . import admin
from .ahelpers import get_users_data, has_admin_rights


@admin.route("/viewBonusPoint", methods=["GET"])
@login_required
def viewBonusPoint():
    """Handles bonus points overview page for all users"""

    if not has_admin_rights():
        abort(403)

    users_bonus_points = []

    course_security_code = current_app.config["COURSE_SECURITY_CODE"]
    users_lst = get_users_data(course_security_code)
    exercises = get_exercises(part=PART_BONUS)

    for user_json in users_lst:
        user_json["bonuses"], user_json["bonus_total"] = get_user_bonus_points(
            exercises, user_json["itid"]
        )
        users_bonus_points.append(user_json)

    return render_template(
        "admin/admin_bonus_ui.html",
        usersBonusPoints=users_bonus_points,
        exercises=exercises,
        menu="admin",
    )


@admin.route("/editBonusPointUser", methods=["GET", "POST"])
@login_required
def editBonusPointUser():
    """Handles edit of user bonus points"""

    if not has_admin_rights():
        abort(403)

    info_message = request.values.get("message")

    user_id = request.values.get("user")
    exercise = get_exercise(request.values.get("exerciseCode"))
    user_db = db.session.query(Users).filter(Users.itid == user_id).first()
    if exercise is None or user_db is None:
        abort(404)

    user_json = to_json_sqla(user_db)
    user_json["name"] = email_to_name(user_json["email"])

    if request.method == "POST":
        info_message = process_edit_request_db(request, exercise.itid)

    bonus_point_entry = get_latest_bonus_points(user_db.itid, exercise.itid)
    bonus_json = {}
    if bonus_point_entry:
        bonus_json = to_json_sqla(bonus_point_entry)
    else:
        bonus_json["visible"] = True
        bonus_json["is_addable"] = True

    bonus_json["exercise_name"] = exercise.name
    bonus_json["exercise_code"] = exercise.code
    bonus_json["max_points"] = exercise.bonus_max_points

    return render_template(
        "admin/admin_bonus_edit.html",
        message=info_message,
        user=user_json,
        bonus=bonus_json,
        menu="admin",
    )


def process_edit_request_db(request, exercise_id: int) -> str:
    """Saves the bonus points from the edit form

    Args:
        request (_type_): HTTP request
        exercise_id (int): id of the exercise

    Returns:
        str: status of the save
    """

    try:
        points = float(request.form["bonusPointValue"].replace(",", "."))
    except ValueError:
        return "[x] Bonus points must be a number"

    new_bonus_point = ExerciseBonusPoints(
        user_id=request.form["user"],
        exercise_id=exercise_id,
        points=points,
        is_addable="checkIsAddableSubmitted" in request.form,
        visible="checkBonusPointVisible" in request.form,
    )
    db.session.add(new_bonus_point)
    db.session.commit()

    return "New bonus point was saved"
