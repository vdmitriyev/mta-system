from datetime import datetime

from app.exercises import (
    EXERCISE_COLUMNS,
    PART_BONUS,
    PART_REVIEW,
    exercise_csv_row,
    exercises_csv,
    get_exercise,
    get_exercises,
    get_latest_bonus_points,
    get_latest_review,
    get_user_bonus_points,
    get_user_reviews,
    render_review_content,
)
from app.models import ExerciseBonusPoints, ExerciseReviews
from app.visibility import (
    DEFAULT_UI_VISIBILITY_SETTINGS,
    add_default_ui_visibility_settings,
    change_ui_visibility_settings,
    ui_visibility_rows,
    ui_visibility_settings,
)
from tests.conftest import add_exercise, add_user


def test_exercises_are_filtered_and_ordered(db):
    add_exercise(db, "B", order=2, has_review=False)
    add_exercise(db, "A", order=1, has_bonus=False)
    add_exercise(db, "C", order=3, visible=False)

    assert [e.code for e in get_exercises(db)] == ["A", "B", "C"]
    assert [e.code for e in get_exercises(db, part=PART_REVIEW)] == ["A", "C"]
    assert [e.code for e in get_exercises(db, part=PART_BONUS)] == ["B", "C"]
    assert [e.code for e in get_exercises(db, PART_REVIEW, only_visible=True)] == ["A"]
    assert get_exercise(db, "B").code == "B"
    assert get_exercise(db, "none") is None


def test_newest_review_is_valid(db):
    user, exercise = add_user(db), add_exercise(db)
    assert get_latest_review(db, user.itid, exercise.itid) is None
    for content in ("first", "second"):
        db.add(
            ExerciseReviews(
                user_id=user.itid, exercise_id=exercise.itid, content=content
            )
        )
        db.commit()
    assert get_latest_review(db, user.itid, exercise.itid).content == "second"


def test_review_markdown_is_rendered(db):
    review = ExerciseReviews(content="**good** work", render_format="MARKDOWN")
    assert "<strong>good</strong>" in render_review_content(review)
    plain = ExerciseReviews(content="**plain**", render_format="TEXT")
    assert render_review_content(plain) == "**plain**"
    assert (
        render_review_content(ExerciseReviews(content=None, render_format="MARKDOWN"))
        == ""
    )


def test_user_reviews(db):
    user = add_user(db)
    first, second = add_exercise(db, "EX1"), add_exercise(db, "EX2", order=2)
    db.add(
        ExerciseReviews(
            user_id=user.itid,
            exercise_id=first.itid,
            content="ok",
            submitted=True,
            reviewed=False,
            visible=True,
        )
    )
    db.commit()

    reviews = get_user_reviews(db, [first, second], user.itid)
    assert (
        reviews[0]["submitted"] and reviews[0]["has_content"] and reviews[0]["visible"]
    )
    assert not reviews[0]["reviewed"]
    assert "ok" in reviews[0]["content"]
    assert reviews[1] == {
        "code": "EX2",
        "name": "Exercise 1",
        "has_content": False,
        "submitted": False,
        "reviewed": False,
        "visible": False,
        "content": None,
    }


def test_bonus_points_total_counts_only_addable_points(db):
    user = add_user(db)
    first = add_exercise(db, "EX1")
    second = add_exercise(db, "EX2", order=2)
    third = add_exercise(db, "EX3", order=3)

    db.add(ExerciseBonusPoints(user_id=user.itid, exercise_id=first.itid, points=1.0))
    db.commit()
    db.add(ExerciseBonusPoints(user_id=user.itid, exercise_id=first.itid, points=3.5))
    db.add(
        ExerciseBonusPoints(
            user_id=user.itid, exercise_id=second.itid, points=2.0, is_addable=False
        )
    )
    db.add(
        ExerciseBonusPoints(
            user_id=user.itid, exercise_id=third.itid, points=9.0, deleted=True
        )
    )
    db.commit()

    bonuses, total = get_user_bonus_points(db, [first, second, third], user.itid)
    assert total == 3.5
    assert [item["points"] for item in bonuses] == [3.5, 2.0, 0.0]
    assert [item["is_set"] for item in bonuses] == [True, True, False]
    assert bonuses[0]["max_points"] == 5.0
    assert get_latest_bonus_points(db, user.itid, third.itid) is None


def test_default_visibility_settings_are_added_once(db):
    add_default_ui_visibility_settings(db)
    add_default_ui_visibility_settings(db)
    settings = ui_visibility_settings(db)
    assert len(settings) == len(DEFAULT_UI_VISIBILITY_SETTINGS)
    # all are shown at the start, only the page Downloads is off
    assert [key for key, visible in settings.items() if not visible] == ["downloads"]
    assert len(ui_visibility_rows(db)) == len(settings)


def test_changed_visibility_is_kept(db):
    add_default_ui_visibility_settings(db)
    assert change_ui_visibility_settings(db, "bonus", False) is True
    add_default_ui_visibility_settings(db)
    assert ui_visibility_settings(db)["bonus"] is False
    assert change_ui_visibility_settings(db, "no-such-key", True) is False


def test_default_visibility_needs_the_table(settings, tmp_path):
    from app.database import init_engine, session_scope

    init_engine(settings.database_url)
    with session_scope() as empty_db:
        add_default_ui_visibility_settings(empty_db)


def test_exercise_as_csv_row(db):
    exercise = add_exercise(
        db,
        "EX1",
        submission_deadline=datetime(2026, 11, 30, 23, 59),
        bonus_max_points=5.0,
        has_submission=True,
    )
    row = exercise_csv_row(exercise)
    assert list(row) == list(EXERCISE_COLUMNS)
    assert row["submission_deadline"] == "2026-11-30T23:59:00"
    assert (row["bonus_max_points"], row["year"], row["description"]) == ("5", "", "")
    assert (row["has_submission"], row["submission_email"]) == ("true", "false")

    exercise.bonus_max_points = 2.5
    assert exercise_csv_row(exercise)["bonus_max_points"] == "2.5"


def test_exercises_csv_has_all_exercises_in_order(db):
    add_exercise(db, "B", order=2, visible=False)
    add_exercise(db, "A", order=1)
    lines = exercises_csv(db).splitlines()
    assert lines[0] == ";".join(EXERCISE_COLUMNS)
    assert [line.split(";")[0] for line in lines[1:]] == ["A", "B"]
