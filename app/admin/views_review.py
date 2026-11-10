import copy

from flask import abort, current_app, render_template, request
from flask_login import login_required

from ..extensions import db
from ..main.exercises_helpers import (
    PART_REVIEW,
    get_exercise,
    get_exercises,
    get_latest_review,
    render_review_content,
)
from ..main.mhelpers import email_to_name
from ..models import ExerciseReviews, Users
from ..utils.uhelpers import to_json_sqla
from . import admin
from .ahelpers import get_users_data, has_admin_rights


@admin.route("/viewReview", methods=["GET"])
@login_required
def viewReview():
    """Handles review view"""

    if not has_admin_rights():
        abort(403)
    users_review = []

    course_security_code = current_app.config["COURSE_SECURITY_CODE"]
    users_lst = get_users_data(course_security_code)
    exercises = get_exercises(part=PART_REVIEW)

    for user_json in users_lst:

        user_exercises = []
        for value in exercises.values():
            # FIXME: optimize query
            new_value = copy.deepcopy(value)
            review = get_latest_review(user_json["itid"], value["itid"])
            if review is not None:
                new_value["review_available"] = bool(review.content)
                new_value["submitted"] = review.submitted
                new_value["reviewed"] = review.reviewed
                new_value["review_visible"] = review.visible

            user_exercises.append(new_value)

        user_json["exercises"] = user_exercises
        users_review.append(user_json)

    return render_template(
        "admin/admin_review_ui.html",
        usersReview=users_review,
        exercises=exercises,
        menu="admin",
    )


@admin.route("/editReviewUser", methods=["GET", "POST"])
@login_required
def editReviewUser():
    """Handles edit user review"""

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

    review_db = get_latest_review(user_db.itid, exercise.itid)
    review_json = {}
    if review_db:
        review_json = to_json_sqla(review_db)
        review_json["content_rendered"] = render_review_content(review_json)
    else:
        review_json["submitted"] = True
        review_json["reviewed"] = True
        review_json["visible"] = True

    review_json["exercise_name"] = exercise.name
    review_json["exercise_code"] = exercise.code

    return render_template(
        "admin/admin_review_edit.html",
        message=info_message,
        user=user_json,
        review=review_json,
        menu="admin",
    )


def process_edit_request_db(request, exercise_id: int) -> str:
    """Saves the review from the edit form

    Args:
        request (_type_): HTTP request
        exercise_id (int): id of the exercise

    Returns:
        str: status of the save
    """

    new_review = ExerciseReviews(
        content=request.form["txtContent"],
        user_id=request.form["user"],
        exercise_id=exercise_id,
        submitted="checkAnswerSubmitted" in request.form,
        reviewed="checkAnswerReviewed" in request.form,
        visible="checkReviewVisible" in request.form,
    )
    db.session.add(new_review)
    db.session.commit()

    return "New feedback was saved"
