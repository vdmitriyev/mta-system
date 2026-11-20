"""Admin page Downloads: files that the users can download"""

from fastapi import APIRouter, Depends, HTTPException, Request

from app import downloads
from app.admin_log import log_action
from app.config import DOWNLOAD_MAX_MB
from app.models import Downloads
from app.security import csrf_protect
from app.submissions import Upload, format_size
from app.web import Page, flash, limit_upload, redirect, require_admin

router = APIRouter(
    prefix="/mtas-admin/downloads",
    include_in_schema=False,
    dependencies=[Depends(require_admin)],
)


limit_download_size = limit_upload(lambda: downloads.max_bytes())


async def download_form(request: Request) -> dict:
    """The fields of the form, and the file (None: no file chosen)"""

    form = await request.form()
    item = form.get("file")
    upload = None
    if hasattr(item, "file") and item.filename:
        upload = Upload(filename=item.filename, file=item.file)
    return {
        "id": form.get("id", ""),
        "title": str(form.get("title", "")).strip()[:200],
        "description": str(form.get("description", "")).strip(),
        "exercise": str(form.get("exercise", "")).strip(),
        "visible": form.get("visible") in ("on", "true", "1"),
        "upload": upload,
    }


def item_or_404(page: Page, item_id) -> Downloads:
    item = downloads.get_download(page.db, item_id) if str(item_id).isdigit() else None
    if item is None:
        raise HTTPException(status_code=404)
    return item


def exercise_id(page: Page, code: str) -> int | None:
    """Exercise with bonus points of the form; empty: none"""

    if not code:
        return None
    for exercise in downloads.bonus_exercises(page.db):
        if exercise.code == code:
            return exercise.itid
    raise HTTPException(status_code=400)


def _context(page: Page) -> dict:
    return {
        "exercises": downloads.bonus_exercises(page.db),
        "max_mb": DOWNLOAD_MAX_MB,
        "accept": ",".join(downloads.ALLOWED_TYPES),
        "allowed": downloads.ALLOWED_TEXT,
        "format_size": format_size,
    }


@router.get("")
def downloads_page(page: Page = Depends()):
    items = downloads.list_downloads(page.db)
    exercises = {
        exercise.itid: exercise for exercise in downloads.bonus_exercises(page.db)
    }
    return page.render(
        "admin/downloads.html",
        items=items,
        exercise_of=exercises,
        enabled=page.visibility.get("downloads", False),
        **_context(page),
    )


@router.post("/add", dependencies=[Depends(limit_download_size), Depends(csrf_protect)])
def download_add(page: Page = Depends(), form: dict = Depends(download_form)):
    if form["upload"] is None:
        flash(page.request, "Choose a file.", "danger")
        return redirect("/mtas-admin/downloads")
    linked = exercise_id(page, form["exercise"])
    try:
        stored = downloads.store_file(form["upload"])
    except downloads.DownloadError as error:
        flash(page.request, str(error), "danger")
        return redirect("/mtas-admin/downloads")
    item = downloads.add_download(
        page.db, stored, form["title"], form["description"], linked, form["visible"]
    )
    log_action(
        page.db,
        page.user,
        "download_added",
        exercise_code=form["exercise"] or None,
        details=f"{item.title}: {item.original_name}",
    )
    flash(page.request, f"Added: {item.title}", "success")
    return redirect("/mtas-admin/downloads")


@router.get("/edit")
def download_edit_form(id: int, page: Page = Depends()):
    item = item_or_404(page, id)
    return page.render("admin/download_edit.html", item=item, **_context(page))


@router.post(
    "/edit", dependencies=[Depends(limit_download_size), Depends(csrf_protect)]
)
def download_edit(page: Page = Depends(), form: dict = Depends(download_form)):
    item = item_or_404(page, form["id"])
    if not form["title"]:
        flash(page.request, "Enter a title.", "danger")
        return redirect(f"/mtas-admin/downloads/edit?id={item.itid}")
    linked = exercise_id(page, form["exercise"])
    if form["upload"] is not None:
        try:
            stored = downloads.store_file(form["upload"])
        except downloads.DownloadError as error:
            flash(page.request, str(error), "danger")
            return redirect(f"/mtas-admin/downloads/edit?id={item.itid}")
        downloads.replace_file(page.db, item, stored)
    item.title = form["title"]
    item.description = form["description"] or None
    item.exercise_id = linked
    item.visible = form["visible"]
    page.db.commit()
    log_action(
        page.db,
        page.user,
        "download_changed",
        exercise_code=form["exercise"] or None,
        details=f"{item.title}: {item.original_name}"
        + (" (new file)" if form["upload"] else ""),
    )
    flash(page.request, f"Saved: {item.title}", "success")
    return redirect("/mtas-admin/downloads")


@router.post("/move", dependencies=[Depends(csrf_protect)])
async def download_move(request: Request, page: Page = Depends()):
    form = await request.form()
    item = item_or_404(page, form.get("id", ""))
    step = -1 if form.get("direction") == "up" else 1
    if downloads.move(page.db, item, step):
        log_action(
            page.db,
            page.user,
            "download_moved",
            details=f"{item.title}: {'up' if step < 0 else 'down'}",
        )
    return redirect("/mtas-admin/downloads")


@router.post("/delete", dependencies=[Depends(csrf_protect)])
async def download_delete(request: Request, page: Page = Depends()):
    form = await request.form()
    item = item_or_404(page, form.get("id", ""))
    title, name = item.title, item.original_name
    downloads.delete_download(page.db, item)
    log_action(page.db, page.user, "download_deleted", details=f"{title}: {name}")
    flash(page.request, f"Deleted: {title}", "success")
    return redirect("/mtas-admin/downloads")


@router.get("/file/{item_id}")
def download_file(item_id: int, page: Page = Depends()):
    return downloads.file_response(item_or_404(page, item_id))
