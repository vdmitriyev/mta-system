"""Page Downloads of a logged-in user"""

from fastapi import APIRouter, Depends, HTTPException

from app import downloads
from app.models import Users
from app.submissions import format_size
from app.web import Page, require_user

router = APIRouter(prefix="/downloads", include_in_schema=False)


def require_visible(page: Page = Depends()) -> None:
    """The admin switches the page on (Visibility: Downloads)"""

    if not page.visibility.get("downloads"):
        raise HTTPException(status_code=404)


@router.get("", dependencies=[Depends(require_visible)])
def downloads_page(page: Page = Depends(), user: Users = Depends(require_user)):
    return page.render(
        "downloads.html",
        rows=downloads.user_downloads(page.db, user.itid),
        format_size=format_size,
    )


@router.get("/file/{item_id}", dependencies=[Depends(require_visible)])
def download_file(
    item_id: int, page: Page = Depends(), user: Users = Depends(require_user)
):
    item = downloads.get_download(page.db, item_id)
    if item is None or not item.visible:
        raise HTTPException(status_code=404)
    return downloads.file_response(item)
