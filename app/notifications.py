"""Notifications for the users: shown on the page Account, counted on the gear icon.

Admins write messages (and can send them by e-mail: first a test to themselves, then
to the users). The app adds automatic notifications for events (setting NOTIFICATIONS_AUTO):
a service, a dataset or a page is shown, a download or a survey is added, a new version.
Automatic notifications start hidden: an admin shows them on the page Notifications.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import (
    String,
    and_,
    cast,
    event,
    func,
    insert,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import Session

from app import __version__, markdown_text
from app.config import get_settings
from app.emails import SUBJECT_PREFIX, Mailer, render_text, send_email
from app.models import (
    SERVICE_MODELS,
    EmailBatch,
    EmailBatchItem,
    Notification,
    NotificationEmail,
    NotificationRead,
    SurveyAssignment,
    Users,
)
from app.timeutil import utc_now
from app.users import course_users
from app.visibility import SERVICE_CARD, VISIBILITY_INFO

MESSAGE = "message"
KIND_LABELS = {
    MESSAGE: "Message",
    "service": "New service",
    "dataset": "New dataset",
    "page": "New page",
    "download": "New download",
    "survey": "New survey",
    "version": "New version",
}
MAX_SHOWN = 50

# menu entries of the users: ui_key -> name
PAGES = {
    "downloads": "Downloads",
    "submissions": "Submissions",
    "reviews": "Reviews",
    "bonus": "Bonus points",
}

logger = logging.getLogger(__name__)


def notify(
    db: Session,
    kind: str,
    title: str,
    body: str = "",
    audience: str | None = None,
    event_key: str | None = None,
) -> bool:
    """Adds a hidden notification: an admin shows it. Returns False if the event
    is switched off or known already.

    The caller commits. event_key: the same event gives only one notification.
    """

    if kind not in get_settings().notifications_auto:
        return False
    values = {
        "kind": kind,
        "title": title[:200],
        "body": body or None,
        "audience": audience,
        "event_key": event_key,
        "hidden": True,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    # "OR IGNORE" (SQLite): a known event_key adds nothing, also with several workers
    result = db.execute(insert(Notification.__table__).prefix_with("OR IGNORE"), values)
    return result.rowcount > 0


# ---- what a user sees ----


AUDIENCE_CACHE = "notification_audiences"


@event.listens_for(Session, "after_commit")
def _forget_audiences(session: Session) -> None:
    session.info.pop(AUDIENCE_CACHE, None)


def audiences_of(db: Session, user: Users) -> list[str]:
    """The groups of the user: services with an account, surveys.

    One query, kept in the session until the next commit (the gear icon and the
    page Account need it in the same request).
    """

    cache = db.info.setdefault(AUDIENCE_CACHE, {})
    if user.itid in cache:
        return cache[user.itid]
    parts = [
        select(literal(f"service:{service}"))
        .where(model.user_id == user.itid, model.deleted.is_(False))
        .limit(1)
        for service, model in SERVICE_MODELS.items()
    ]
    parts.append(
        select(literal("survey:") + cast(SurveyAssignment.survey_id, String)).where(
            SurveyAssignment.user_id == user.itid
        )
    )
    query = union_all(*[part.subquery().select() for part in parts])
    cache[user.itid] = [row[0] for row in db.execute(query)]
    return cache[user.itid]


def _visible_to(db: Session, user: Users):
    """A new user starts without notifications: only the ones shown after the
    registration (and the ones for this user only)"""

    return and_(
        Notification.hidden.is_(False),
        Notification.shown_at.is_not(None),
        or_(Notification.user_id.is_(None), Notification.user_id == user.itid),
        or_(
            Notification.audience.is_(None),
            Notification.audience.in_(audiences_of(db, user)),
        ),
        or_(
            Notification.user_id.is_not(None),
            Notification.shown_at >= (user.created_at or datetime.min),
        ),
    )


def show(item: Notification, shown: bool = True) -> None:
    """Shows (or hides) a notification. The caller commits."""

    item.hidden = not shown
    if shown and item.shown_at is None:
        item.shown_at = utc_now()


def _read_ids(db: Session, user: Users):
    return db.query(NotificationRead.notification_id).filter(
        NotificationRead.user_id == user.itid
    )


def for_user(db: Session, user: Users, limit: int = MAX_SHOWN) -> list[dict]:
    """The newest notifications of the user: [{"item": Notification, "read": bool}]"""

    items = (
        db.query(Notification)
        .filter(_visible_to(db, user))
        .order_by(Notification.shown_at.desc(), Notification.itid.desc())
        .limit(limit)
        .all()
    )
    read = {row[0] for row in _read_ids(db, user)}
    return [{"item": item, "read": item.itid in read} for item in items]


def unread_count(db: Session, user: Users) -> int:
    return (
        db.query(func.count(Notification.itid))
        .filter(_visible_to(db, user), Notification.itid.not_in(_read_ids(db, user)))
        .scalar()
    )


def mark_read(db: Session, user: Users, notification_id: int) -> bool:
    """Marks one notification as read. False: the user cannot see it."""

    visible = (
        db.query(Notification.itid)
        .filter(Notification.itid == notification_id, _visible_to(db, user))
        .first()
    )
    if visible is None:
        return False
    db.execute(
        insert(NotificationRead).prefix_with("OR IGNORE"),
        {"notification_id": notification_id, "user_id": user.itid},
    )
    db.commit()
    return True


def mark_all_read(db: Session, user: Users) -> int:
    unread = (
        db.query(Notification.itid)
        .filter(_visible_to(db, user), Notification.itid.not_in(_read_ids(db, user)))
        .all()
    )
    if unread:
        db.execute(
            insert(NotificationRead).prefix_with("OR IGNORE"),
            [{"notification_id": row[0], "user_id": user.itid} for row in unread],
        )
        db.commit()
    return len(unread)


# ---- admin ----


def read_counts(db: Session) -> dict:
    """notification_id -> number of users who read it"""

    rows = db.query(
        NotificationRead.notification_id, func.count(NotificationRead.itid)
    ).group_by(NotificationRead.notification_id)
    return dict(rows.all())


def audience_user_ids(db: Session, audience: str) -> set[int]:
    group, _, name = audience.partition(":")
    if group == "service" and name in SERVICE_MODELS:
        return set(_users_with(db, name))
    if group == "survey" and name.isdigit():
        rows = db.query(SurveyAssignment.user_id).filter(
            SurveyAssignment.survey_id == int(name)
        )
        return {row[0] for row in rows}
    return set()


def audience_label(audience: str | None) -> str:
    if audience is None:
        return "All users"
    group, _, name = audience.partition(":")
    if group == "service":
        return f"Users of {name}"
    if group == "survey":
        return f"Users with survey {name}"
    return audience


def recipients(
    db: Session,
    user_ids: list[int] | None = None,
    notification: Notification | None = None,
) -> list[Users]:
    """Users of the course who can get e-mails (all, or only the given ones),
    only the users of the notification's group"""

    users = [u for u in course_users(db) if u.is_user_assigned and u.active]
    if notification is not None and notification.user_id is not None:
        users = [u for u in users if u.itid == notification.user_id]
    elif notification is not None and notification.audience:
        group = audience_user_ids(db, notification.audience)
        users = [u for u in users if u.itid in group]
    if user_ids is not None:
        wanted = set(user_ids)
        users = [u for u in users if u.itid in wanted]
    return users


def email_text(notification: Notification) -> str:
    """The plain text part: the Markdown as written, in the frame of
    app/templates/emails/notification.txt (greeting and signature)"""

    text = notification.body or notification.title
    return render_text("notification", text=text)


def email_html(notification: Notification) -> str:
    return markdown_text.to_html(email_text(notification))


def default_subject(notification: Notification) -> str:
    return f'Notification about "{notification.title}"'


def email_subject(notification: Notification) -> str:
    """The subject without the prefix [MTA-SYSTEM] (the e-mail adds it)"""

    return notification.email_subject or default_subject(notification)


def _start_batch(
    db: Session, notification: Notification, kind: str, admin_id: int | None
) -> EmailBatch:
    """The e-mail as sent, for the page E-mail history"""

    batch = EmailBatch(
        notification_id=notification.itid,
        kind=kind,
        subject=f"{SUBJECT_PREFIX} {email_subject(notification)}",
        body=email_text(notification),
        created_by=admin_id,
    )
    db.add(batch)
    db.commit()
    return batch


def _note(db: Session, batch: EmailBatch, user: Users, error: str | None) -> None:
    db.add(
        EmailBatchItem(
            batch_id=batch.itid,
            user_id=user.itid,
            email=user.email,
            status=FAILED if error else SENT,
            error=(error or None) and error[:300],
            sent_at=utc_now(),
        )
    )


def send_test_email(db: Session, notification: Notification, admin: Users) -> bool:
    """Sends the e-mail to the admin as a test (optional)"""

    batch = _start_batch(db, notification, "test", admin.itid)
    sent = send_email(
        admin.email,
        email_subject(notification),
        email_text(notification),
        get_settings(),
        html=email_html(notification),
    )
    _note(db, batch, admin, None if sent else "not sent: see the log of the app")
    batch.finished_at = utc_now()
    db.commit()
    if not sent:
        return False
    notification.email_test_at = utc_now()
    notification.email_test_to = admin.email
    db.commit()
    return True


# who gets the e-mail: the users of the group who did not get it yet (also the
# failed ones), all of them again, or the chosen users
MISSING, ALL, SELECTED = "missing", "all", "selected"
SENDING, SENT, FAILED = "sending", "sent", "failed"
# a "sending" row older than this belongs to a task that stopped
SENDING_TIMEOUT = timedelta(hours=1)


def sent_user_ids(db: Session, notification_id: int) -> set[int]:
    rows = db.query(NotificationEmail.user_id).filter(
        NotificationEmail.notification_id == notification_id,
        NotificationEmail.status == SENT,
    )
    return {row[0] for row in rows}


def email_recipients(
    db: Session, notification: Notification, mode: str, user_ids=None
) -> list[Users]:
    users = recipients(db, user_ids if mode == SELECTED else None, notification)
    if mode == MISSING:
        sent = sent_user_ids(db, notification.itid)
        users = [user for user in users if user.itid not in sent]
    return users


def email_state(db: Session, notification_id: int) -> dict:
    """{"sent": n, "failed": [NotificationEmail], "sending": n}"""

    rows = (
        db.query(NotificationEmail)
        .filter(NotificationEmail.notification_id == notification_id)
        .order_by(NotificationEmail.email)
        .all()
    )
    return {
        "sent": sum(1 for row in rows if row.status == SENT),
        "failed": [row for row in rows if row.status == FAILED],
        "sending": sum(1 for row in rows if row.status == SENDING),
    }


def _claim(db: Session, notification_id: int, user: Users, again: bool) -> bool:
    """Marks the e-mail to the user as "sending". False: sent already, or another
    task sends it now. Two clicks on "Send" do not give two e-mails."""

    values = {"status": SENDING, "email": user.email, "error": None}
    added = db.execute(
        insert(NotificationEmail.__table__).prefix_with("OR IGNORE"),
        {"notification_id": notification_id, "user_id": user.itid, **values},
    )
    if added.rowcount:
        db.commit()
        return True
    free = [
        NotificationEmail.status == FAILED,
        and_(
            NotificationEmail.status == SENDING,
            NotificationEmail.updated_at < utc_now() - SENDING_TIMEOUT,
        ),
    ]
    if again:
        free.append(NotificationEmail.status == SENT)
    claimed = (
        db.query(NotificationEmail)
        .filter(
            NotificationEmail.notification_id == notification_id,
            NotificationEmail.user_id == user.itid,
            or_(*free),
        )
        .update({**values, "updated_at": utc_now()}, synchronize_session=False)
    )
    db.commit()
    return claimed > 0


def email_users_task(
    db: Session,
    notification_id: int,
    mode: str,
    user_ids: list | None = None,
    admin_id: int | None = None,
) -> str:
    """Background task: sends the notification to the users over one SMTP
    connection, and notes the result per user (see app/tasks.py)"""

    from app.tasks import TaskError

    notification = db.get(Notification, notification_id)
    if notification is None:
        raise TaskError("The notification was deleted")
    users = email_recipients(db, notification, mode, user_ids)
    subject, text = email_subject(notification), email_text(notification)
    html = email_html(notification)
    batch = _start_batch(db, notification, "users", admin_id)
    sent, failed, skipped = 0, [], 0
    with Mailer(get_settings()) as mailer:
        for user in users:
            if not _claim(db, notification_id, user, again=mode != MISSING):
                skipped += 1
                continue
            error = mailer.send(user.email, subject, text, html)
            db.query(NotificationEmail).filter(
                NotificationEmail.notification_id == notification_id,
                NotificationEmail.user_id == user.itid,
            ).update(
                {
                    "status": FAILED if error else SENT,
                    "error": (error or None) and error[:300],
                    "updated_at": utc_now(),
                },
                synchronize_session=False,
            )
            _note(db, batch, user, error)
            db.commit()
            if error:
                failed.append(user.email)
            else:
                sent += 1
    batch.finished_at = notification.emailed_at = utc_now()
    notification.emailed_count = len(sent_user_ids(db, notification_id))
    db.commit()
    message = f"“{notification.title}” was sent to {sent} users"
    if failed:
        message += f"; not sent to {len(failed)}: {', '.join(failed[:10])}"
    if skipped:
        message += f"; {skipped} skipped (sent already or by another task)"
    return message


# ---- automatic notifications ----


def _users_with(db: Session, service: str) -> list[int]:
    model = SERVICE_MODELS[service]
    rows = db.query(model.user_id).filter(model.deleted.is_(False)).distinct()
    return [row[0] for row in rows if row[0] is not None]


def visibility_switched_on(db: Session, ui_key: str) -> int:
    """An admin showed a part of the UI: a notification for the users who can
    use it (hidden until an admin shows it).

    Returns the number of new notifications. The caller commits.
    """

    item = VISIBILITY_INFO.get(ui_key)
    if item is None:
        return 0
    today = date.today().isoformat()
    if item.label == SERVICE_CARD and ui_key in SERVICE_MODELS:
        title, kind, service = f"New service: {item.group}", "service", ui_key
        body = f"{item.group} is now on the page Services, with your login."
    elif ui_key.startswith("importers_"):
        name = item.label.split(":", 1)[-1].strip()
        title, kind, service = f"New dataset: {name}", "dataset", "postgresql"
        body = (
            f"You can import the dataset {name} into your PostgreSQL database "
            "on the page Services."
        )
    elif ui_key in PAGES:
        added = notify(
            db,
            "page",
            f"New page: {PAGES[ui_key]}",
            f"The menu has a new entry: {PAGES[ui_key]}.",
            event_key=f"visibility:{ui_key}:{today}",
        )
        return int(added)
    else:
        return 0
    added = notify(
        db,
        kind,
        title,
        body,
        audience=f"service:{service}",
        event_key=f"visibility:{ui_key}:{today}",
    )
    return int(added)


def download_added(db: Session, item, page_visible: bool) -> bool:
    """A visible download (on a visible page Downloads) is new for the users"""

    if not (item.visible and page_visible):
        return False
    return notify(
        db,
        "download",
        f"New download: {item.title}",
        item.description or "",
        event_key=f"download:{item.itid}",
    )


def survey_given(db: Session, survey_id: int, title: str) -> bool:
    """One notification per survey, for all users who got it"""

    return notify(
        db,
        "survey",
        f"New survey: {title}" if title else "New survey",
        "Take part in the survey on the page Services.",
        audience=f"survey:{survey_id}",
        event_key=f"survey:{survey_id}",
    )


def new_version(db: Session) -> bool:
    """Once per version of the app (at the start), hidden until an admin shows it"""

    added = notify(
        db,
        "version",
        f"New version {__version__}",
        "The system was updated. The page About shows the services and their versions.",
        event_key=f"version:{__version__}",
    )
    db.commit()
    return added
