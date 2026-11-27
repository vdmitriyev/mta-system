"""Pages of a logged-in user: files that the user submits for the exercises"""

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse

from app import submissions, surveys
from app.config import get_settings
from app.models import Exercises, Users
from app.security import csrf_protect
from app.web import Page, flash, limit_upload, redirect, require_user, send_file

router = APIRouter(prefix="/submissions", include_in_schema=False)


limit_upload_size = limit_upload(lambda: submissions.max_bytes())


async def uploaded_files(request: Request) -> list:
    form = await request.form()
    return [
        submissions.Upload(filename=item.filename or "", file=item.file)
        for item in form.getlist("files")
        if hasattr(item, "file")
    ]


def submission_exercise(page: Page, code: str) -> Exercises:
    """The exercise, if the user can submit files for it"""

    for exercise in submissions.submission_exercises(page.db):
        if exercise.code == code:
            return exercise
    raise HTTPException(status_code=404)


def require_visible(page: Page = Depends()) -> None:
    if not page.visibility.get("submissions"):
        raise HTTPException(status_code=404)


@router.get("", dependencies=[Depends(require_visible)])
def submissions_page(page: Page = Depends(), user: Users = Depends(require_user)):
    items = []
    for exercise in submissions.submission_exercises(page.db):
        deadline = submissions.effective_deadline(page.db, exercise, user.itid)
        items.append(
            {
                "exercise": exercise,
                "deadline": deadline,
                "extended": deadline != exercise.submission_deadline,
                "open": submissions.is_open(deadline),
                "files": submissions.active_submissions(
                    page.db, user.itid, exercise.itid
                ),
            }
        )
    return page.render(
        "submissions.html",
        items=items,
        blocked=surveys.feature_blocked(page.db, user.itid, surveys.SUBMISSIONS),
        survey_status_text=surveys.STATUS_TEXT,
        max_mb=get_settings().submission_max_file_mb,
        max_files=get_settings().submission_max_files,
        accept=",".join(submissions.ALLOWED_TYPES),
        format_size=submissions.format_size,
    )


@router.get("/too-large")
def too_large(page: Page = Depends(), user: Users = Depends(require_user)):
    """nginx shows this page when an upload is too large"""

    flash(
        page.request,
        f"The upload is too large. One upload can have at most "
        f"{get_settings().submission_max_file_mb} MB.",
        "danger",
    )
    return redirect("/submissions")


def _send_confirmation(
    background_tasks: BackgroundTasks,
    page: Page,
    user: Users,
    exercise: Exercises,
    action: str,
    files: list,
) -> None:
    if not exercise.submission_email or not files:
        return
    subject, content = submissions.confirmation_email(
        exercise,
        action,
        files,
        submissions.effective_deadline(page.db, exercise, user.itid),
        submissions.active_submissions(page.db, user.itid, exercise.itid),
    )
    background_tasks.add_task(
        submissions.send_confirmation, user.email, subject, content
    )


@router.post(
    "/{code}/upload",
    dependencies=[
        Depends(require_visible),
        Depends(limit_upload_size),
        Depends(csrf_protect),
    ],
)
def upload(
    code: str,
    background_tasks: BackgroundTasks,
    page: Page = Depends(),
    user: Users = Depends(require_user),
    files: list = Depends(uploaded_files),
):
    exercise = submission_exercise(page, code)
    missing = surveys.feature_blocked(page.db, user.itid, surveys.SUBMISSIONS)
    if missing is not None:
        flash(
            page.request,
            f"Complete the survey “{missing.title}” first. Then you can upload files.",
            "danger",
        )
        return redirect("/submissions")
    try:
        saved, errors = submissions.save_uploads(page.db, user, exercise, files)
    except submissions.SubmissionError as error:
        flash(page.request, str(error), "danger")
        return redirect("/submissions")
    for message in errors:
        flash(page.request, message, "danger")
    if saved:
        names = ", ".join(row.original_name for row in saved)
        flash(page.request, f"Submitted: {names}", "success")
    _send_confirmation(background_tasks, page, user, exercise, "upload", saved)
    return redirect("/submissions")


@router.post(
    "/{code}/delete",
    dependencies=[Depends(require_visible), Depends(csrf_protect)],
)
def delete(
    code: str,
    background_tasks: BackgroundTasks,
    page: Page = Depends(),
    user: Users = Depends(require_user),
    submission_id: int = Form(...),
):
    exercise = submission_exercise(page, code)
    try:
        row = submissions.delete_own_submission(page.db, user, exercise, submission_id)
    except submissions.SubmissionError as error:
        flash(page.request, str(error), "danger")
        return redirect("/submissions")
    flash(page.request, f"Deleted: {row.original_name}", "success")
    _send_confirmation(background_tasks, page, user, exercise, "delete", [row])
    return redirect("/submissions")


@router.get("/file/{submission_id}", dependencies=[Depends(require_visible)])
def download(
    submission_id: int, page: Page = Depends(), user: Users = Depends(require_user)
):
    row = submissions.get_submission(page.db, submission_id)
    if row is None or row.deleted or row.user_id != user.itid:
        raise HTTPException(status_code=404)
    return file_response(row)


PDF_TYPE = "application/pdf"


def file_response(row, inline: bool = False) -> FileResponse:
    """The file as a download. inline: a PDF shown in the browser (own tab)."""

    if inline and row.content_type != PDF_TYPE:
        raise HTTPException(status_code=404)
    try:
        path = submissions.file_path(row)
    except submissions.SubmissionError:
        path = None
    return send_file(path, row.content_type, row.original_name, inline)
