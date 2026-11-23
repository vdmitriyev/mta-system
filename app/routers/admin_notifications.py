"""Admin page Notifications: messages for the users, and e-mails with them.

Automatic notifications wait hidden on this page until an admin shows them.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import case, func

from app import notifications
from app.admin_log import log_action
from app.config import get_settings
from app.emails import SUBJECT_PREFIX
from app.models import (
    EmailBatch,
    EmailBatchItem,
    Notification,
    NotificationEmail,
    NotificationRead,
    Users,
)
from app.security import csrf_protect
from app.tasks import enqueue
from app.timeutil import utc_now
from app.web import Page, flash, redirect, require_admin

router = APIRouter(
    prefix="/mtas-admin/notifications",
    include_in_schema=False,
    dependencies=[Depends(require_admin)],
)

PAGE = "/mtas-admin/notifications"


def _item(page: Page, notification_id: int) -> Notification:
    item = page.db.get(Notification, notification_id)
    if item is None:
        raise HTTPException(status_code=404)
    return item


def _back(form, item: Notification):
    """Back to the list (form field back=list) or to the notification"""

    if form.get("back") == "list":
        return redirect(f"{PAGE}#notification-{item.itid}")
    return redirect(f"{PAGE}/{item.itid}")


def _waiting(db):
    return db.query(Notification).filter(Notification.shown_at.is_(None))


def _forget(db, ids: list[int]) -> None:
    """Deleted notifications: their e-mail rows go, the e-mail history stays"""

    db.query(NotificationEmail).filter(
        NotificationEmail.notification_id.in_(ids)
    ).delete(synchronize_session=False)
    db.query(EmailBatch).filter(EmailBatch.notification_id.in_(ids)).update(
        {"notification_id": None}, synchronize_session=False
    )


def _batch_counts(db, batch_ids: list[int]) -> dict:
    """batch itid -> (sent, failed)"""

    rows = (
        db.query(
            EmailBatchItem.batch_id,
            func.sum(case((EmailBatchItem.status == notifications.SENT, 1), else_=0)),
            func.sum(case((EmailBatchItem.status == notifications.FAILED, 1), else_=0)),
        )
        .filter(EmailBatchItem.batch_id.in_(batch_ids))
        .group_by(EmailBatchItem.batch_id)
    )
    return {row[0]: (row[1] or 0, row[2] or 0) for row in rows}


def _admin_emails(db, ids) -> dict:
    ids = {itid for itid in ids if itid}
    if not ids:
        return {}
    return dict(db.query(Users.itid, Users.email).filter(Users.itid.in_(ids)))


def _group_sizes(db, items) -> dict:
    """notification itid -> number of users who can see it"""

    total = len(notifications.recipients(db))
    sizes = {}
    by_audience = {}
    for item in items:
        if item.user_id is not None:
            sizes[item.itid] = 1
        elif item.audience:
            if item.audience not in by_audience:
                by_audience[item.audience] = len(
                    notifications.recipients(db, notification=item)
                )
            sizes[item.itid] = by_audience[item.audience]
        else:
            sizes[item.itid] = total
    return sizes


async def _message_form(request: Request) -> dict:
    form = await request.form()
    title = str(form.get("title", "")).strip()
    if not title:
        raise ValueError("Enter a title.")
    return {
        "title": title[:200],
        "body": str(form.get("body", "")).strip() or None,
    }


@router.get("")
def notifications_page(page: Page = Depends()):
    items = (
        page.db.query(Notification)
        .order_by(Notification.created_at.desc(), Notification.itid.desc())
        .limit(300)
        .all()
    )
    return page.render(
        "admin/notifications.html",
        items=items,
        reads=notifications.read_counts(page.db),
        sizes=_group_sizes(page.db, items),
        waiting=sum(1 for item in items if item.shown_at is None),
        kind_labels=notifications.KIND_LABELS,
        audience_label=notifications.audience_label,
        auto_events=get_settings().notifications_auto,
    )


@router.post("/add", dependencies=[Depends(csrf_protect)])
async def notification_add(request: Request, page: Page = Depends()):
    try:
        values = await _message_form(request)
    except ValueError as error:
        flash(page.request, str(error), "danger")
        return redirect(PAGE)
    item = Notification(
        kind=notifications.MESSAGE,
        created_by=page.user.itid,
        shown_at=utc_now(),
        **values,
    )
    page.db.add(item)
    page.db.commit()
    log_action(page.db, page.user, "notification_added", details=item.title)
    flash(page.request, f"The users see “{item.title}” now.", "success")
    return redirect(f"{PAGE}/{item.itid}")


@router.get("/emails")
def email_history(page: Page = Depends(), notification: int | None = None):
    query = page.db.query(EmailBatch)
    if notification is not None:
        query = query.filter(EmailBatch.notification_id == notification)
    batches = (
        query.order_by(EmailBatch.created_at.desc(), EmailBatch.itid.desc())
        .limit(300)
        .all()
    )
    ids = {batch.notification_id for batch in batches if batch.notification_id}
    titles = dict(
        page.db.query(Notification.itid, Notification.title).filter(
            Notification.itid.in_(ids)
        )
    )
    return page.render(
        "admin/email_history.html",
        batches=batches,
        counts=_batch_counts(page.db, [batch.itid for batch in batches]),
        titles=titles,
        admins=_admin_emails(page.db, [batch.created_by for batch in batches]),
        notification=notification,
    )


@router.get("/emails/{batch_id}")
def email_history_detail(batch_id: int, page: Page = Depends()):
    batch = page.db.get(EmailBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404)
    items = (
        page.db.query(EmailBatchItem)
        .filter(EmailBatchItem.batch_id == batch.itid)
        .order_by(EmailBatchItem.status, EmailBatchItem.email)
        .all()
    )
    item = (
        page.db.get(Notification, batch.notification_id)
        if batch.notification_id
        else None
    )
    return page.render(
        "admin/email_history_detail.html",
        batch=batch,
        items=items,
        notification=item,
        sent=sum(1 for row in items if row.status == notifications.SENT),
        failed=sum(1 for row in items if row.status == notifications.FAILED),
        admin_email=_admin_emails(page.db, [batch.created_by]).get(batch.created_by),
    )


@router.get("/{notification_id}")
def notification_detail(notification_id: int, page: Page = Depends()):
    item = _item(page, notification_id)
    return page.render(
        "admin/notification_detail.html",
        item=item,
        kind_labels=notifications.KIND_LABELS,
        audience_label=notifications.audience_label,
        read_count=notifications.read_counts(page.db).get(item.itid, 0),
        users=notifications.recipients(page.db, notification=item),
        missing=len(
            notifications.email_recipients(page.db, item, notifications.MISSING)
        ),
        email_state=notifications.email_state(page.db, item.itid),
        email_html=notifications.email_html(item),
        email_subject=notifications.email_subject(item),
        default_subject=notifications.default_subject(item),
        subject_prefix=SUBJECT_PREFIX,
        batches=page.db.query(EmailBatch)
        .filter(EmailBatch.notification_id == item.itid)
        .count(),
    )


@router.post("/{notification_id}/edit", dependencies=[Depends(csrf_protect)])
async def notification_edit(
    notification_id: int, request: Request, page: Page = Depends()
):
    item = _item(page, notification_id)
    form = await request.form()
    try:
        values = await _message_form(request)
    except ValueError as error:
        flash(page.request, str(error), "danger")
        return _back(form, item)
    for name, value in values.items():
        setattr(item, name, value)
    item.updated_at = utc_now()
    # the users get the changed text only after a new test
    item.email_test_at = None
    page.db.commit()
    log_action(page.db, page.user, "notification_changed", details=item.title)
    flash(page.request, f"Saved: {item.title}", "success")
    return _back(form, item)


@router.post("/show-waiting", dependencies=[Depends(csrf_protect)])
def notifications_show_waiting(page: Page = Depends()):
    items = _waiting(page.db).all()
    for item in items:
        notifications.show(item)
    page.db.commit()
    for item in items:
        log_action(page.db, page.user, "notification_shown", details=item.title)
    flash(page.request, f"Shown to the users: {len(items)}.", "success")
    return redirect(PAGE)


@router.post("/delete-waiting", dependencies=[Depends(csrf_protect)])
def notifications_delete_waiting(page: Page = Depends()):
    items = _waiting(page.db).all()
    _forget(page.db, [item.itid for item in items])
    for item in items:
        page.db.delete(item)
    page.db.commit()
    for item in items:
        log_action(page.db, page.user, "notification_deleted", details=item.title)
    flash(page.request, f"Deleted: {len(items)}.", "success")
    return redirect(PAGE)


@router.post("/{notification_id}/hide", dependencies=[Depends(csrf_protect)])
async def notification_hide(
    notification_id: int, request: Request, page: Page = Depends()
):
    item = _item(page, notification_id)
    notifications.show(item, shown=item.hidden)
    page.db.commit()
    action = "notification_hidden" if item.hidden else "notification_shown"
    log_action(page.db, page.user, action, details=item.title)
    state = "hidden from" if item.hidden else "shown to"
    flash(page.request, f"“{item.title}” is {state} the users.", "success")
    return _back(await request.form(), item)


@router.post("/{notification_id}/delete", dependencies=[Depends(csrf_protect)])
def notification_delete(notification_id: int, page: Page = Depends()):
    item = _item(page, notification_id)
    title = item.title
    page.db.query(NotificationRead).filter(
        NotificationRead.notification_id == item.itid
    ).delete()
    _forget(page.db, [item.itid])
    page.db.delete(item)
    page.db.commit()
    log_action(page.db, page.user, "notification_deleted", details=title)
    flash(page.request, f"Deleted: {title}", "success")
    return redirect(PAGE)


@router.post("/{notification_id}/email-subject", dependencies=[Depends(csrf_protect)])
async def notification_email_subject(
    notification_id: int, request: Request, page: Page = Depends()
):
    item = _item(page, notification_id)
    form = await request.form()
    subject = " ".join(str(form.get("subject", "")).split())[:200]
    # the default is not stored: it follows a new title
    if subject == notifications.default_subject(item):
        subject = ""
    if (subject or None) != item.email_subject:
        item.email_subject = subject or None
        item.email_test_at = None
        page.db.commit()
        log_action(
            page.db,
            page.user,
            "notification_changed",
            details=f"{item.title}: subject {notifications.email_subject(item)}",
        )
    flash(page.request, f"Subject: {notifications.email_subject(item)}", "success")
    return redirect(f"{PAGE}/{item.itid}#email")


@router.post("/{notification_id}/email-test", dependencies=[Depends(csrf_protect)])
def notification_email_test(notification_id: int, page: Page = Depends()):
    item = _item(page, notification_id)
    if notifications.send_test_email(page.db, item, page.user):
        log_action(page.db, page.user, "notification_test_email", details=item.title)
        flash(
            page.request,
            f"The test e-mail was sent to {page.user.email}. Check it, then send it "
            "to the users.",
            "success",
        )
    else:
        flash(
            page.request,
            "The test e-mail was not sent. Check the e-mail settings (MAIL_*) and "
            "the log.",
            "danger",
        )
    return redirect(f"{PAGE}/{item.itid}#email")


@router.post("/{notification_id}/email-users", dependencies=[Depends(csrf_protect)])
async def notification_email_users(
    notification_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    page: Page = Depends(),
):
    item = _item(page, notification_id)
    back = redirect(f"{PAGE}/{item.itid}#email")
    form = await request.form()
    mode = form.get("audience")
    if mode not in (notifications.ALL, notifications.SELECTED):
        mode = notifications.MISSING
    user_ids = None
    if mode == notifications.SELECTED:
        user_ids = [int(value) for value in form.getlist("user_id") if value.isdigit()]
        if not user_ids:
            flash(page.request, "Choose at least one user.", "danger")
            return back
    count = len(notifications.email_recipients(page.db, item, mode, user_ids))
    if not count:
        flash(page.request, "All users got this e-mail already.", "info")
        return back
    enqueue(
        background_tasks,
        page.db,
        "notification:email",
        notifications.email_users_task,
        item.itid,
        mode,
        user_ids,
        page.user.itid,
        user_id=page.user.itid,
    )
    log_action(
        page.db,
        page.user,
        "notification_emailed",
        details=f"{item.title}: {count} users",
    )
    flash(
        page.request,
        f"The e-mail is sent to {count} users in the background. See the tasks on "
        "the overview page.",
        "success",
    )
    return back
