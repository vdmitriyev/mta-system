"""Notifications: page Account, gear icon, admin page, e-mails, automatic events"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import notifications, surveys
from app.models import (
    AdminActions,
    BackgroundTask,
    Downloads,
    EmailBatch,
    EmailBatchItem,
    MetabaseService,
    Notification,
    NotificationEmail,
    NotificationRead,
)
from app.timeutil import utc_now
from app.visibility import change_ui_visibility_settings
from tests.conftest import (
    ADMIN_EMAIL,
    STUDENT_EMAIL,
    add_postgresql,
    add_user,
    login,
    post,
)

REAL_NEW_VERSION = notifications.new_version


@pytest.fixture(autouse=True)
def no_version_notification(db, monkeypatch):
    """Without the notification of the version (the start of the app adds it)"""

    monkeypatch.setattr(notifications, "new_version", lambda db: False)
    db.query(Notification).delete()
    db.commit()


class SentMails(list):
    """The e-mails of the fakes; addresses in .fail are not sent"""

    def __init__(self):
        super().__init__()
        self.fail = set()
        self.connections = 0


@pytest.fixture
def mails(monkeypatch):
    sent = SentMails()

    def fake_send_email(to_email, subject, content, settings, html=None):
        sent.append(
            {"to": to_email, "subject": subject, "content": content, "html": html}
        )
        return True

    class FakeMailer:
        def __init__(self, settings):
            sent.connections += 1

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def send(self, to_email, subject, content, html=None):
            if to_email in sent.fail:
                return "the server refused the address"
            fake_send_email(to_email, subject, content, None, html)
            return None

    monkeypatch.setattr(notifications, "send_email", fake_send_email)
    monkeypatch.setattr(notifications, "Mailer", FakeMailer)
    return sent


@pytest.fixture
def student_browser(app, student):
    """A second browser: the student, next to admin_client"""

    with TestClient(app) as browser:
        login(browser)
        yield browser


def add_message(db, title="Exam on Friday", **values) -> Notification:
    values.setdefault("shown_at", utc_now())
    item = Notification(kind="message", title=title, **values)
    db.add(item)
    db.commit()
    return item


def gear_count(text: str) -> str | None:
    header = text[: text.index("</header>")]
    if 'class="nav-count"' not in header:
        return None
    start = header.index('class="nav-count"')
    return header[header.index(">", start) + 1 : header.index("</span>", start)]


# ---- page Account and gear icon ----


def test_user_sees_a_message_and_marks_it_as_read(student_client, db):
    item = add_message(db, body="Room A1\nat 10:00")
    text = student_client.get("/account").text
    assert gear_count(text) == "1"
    assert 'id="notifications"' in text and "Exam on Friday" in text
    assert "Room A1<br>\nat 10:00" in text
    assert "only when an admin sends it manually." in text
    # no kind on the page Account
    assert '<span class="badge">Message</span>' not in text
    assert '<span class="badge success">new</span>' in text

    response = post(student_client, f"/account/notifications/{item.itid}/read")
    assert response.headers["location"] == "/account#notifications"
    text = student_client.get("/account").text
    assert gear_count(text) is None
    # still listed, without "new"
    assert "Exam on Friday" in text
    assert '<span class="badge success">new</span>' not in text
    assert '<span class="badge">seen</span>' in text


def test_mark_all_as_read(student_client, db, student):
    for number in range(3):
        add_message(db, title=f"Message {number}")
    assert gear_count(student_client.get("/").text) == "3"
    post(student_client, "/account/notifications/read-all")
    text = student_client.get("/account").text
    assert "3 notifications are marked as read." in text
    assert gear_count(text) is None
    assert notifications.unread_count(db, student) == 0


def test_number_is_on_the_gear_icon(student_client, db):
    add_message(db)
    header = student_client.get("/").text
    gear = header.index('<span class="gear">')
    assert (
        gear
        < header.index('class="nav-count"')
        < header.index('class="nav-icon-label"')
    )


def test_gear_shows_99_plus(student_client, db):
    db.add_all(
        [
            Notification(kind="message", title=f"M{n}", shown_at=utc_now())
            for n in range(120)
        ]
    )
    db.commit()
    assert gear_count(student_client.get("/").text) == "99+"


def test_notification_of_another_user_is_not_shown(student_client, db):
    other = add_user(db, email="other@uni.example", number=7)
    item = add_message(db, title="Only for the other user", user_id=other.itid)
    assert "Only for the other user" not in student_client.get("/account").text
    response = post(student_client, f"/account/notifications/{item.itid}/read")
    assert response.status_code == 404


def test_hidden_notifications_are_not_shown(student_client, db):
    add_message(db, title="Hidden one", hidden=True)
    text = student_client.get("/account").text
    assert "Hidden one" not in text and gear_count(text) is None


def test_new_users_start_without_notifications(db, student):
    old = utc_now() - timedelta(minutes=1)
    student.created_at = utc_now()
    db.add_all(
        [
            Notification(kind="page", title="Old page", shown_at=old),
            Notification(kind="message", title="Old message", shown_at=old),
            Notification(
                kind="survey", title="Old survey", audience="survey:1", shown_at=old
            ),
            Notification(
                kind="message", title="For the user", user_id=student.itid, shown_at=old
            ),
            Notification(kind="page", title="New page", shown_at=utc_now()),
        ]
    )
    db.commit()
    titles = [entry["item"].title for entry in notifications.for_user(db, student)]
    assert sorted(titles) == ["For the user", "New page"]


def test_notifications_can_be_switched_off(student_client, db):
    item = add_message(db)
    change_ui_visibility_settings(db, "notifications", False)
    text = student_client.get("/account").text
    assert gear_count(text) is None and 'id="notifications"' not in text
    assert post(student_client, "/account/notifications/read-all").status_code == 404
    response = post(student_client, f"/account/notifications/{item.itid}/read")
    assert response.status_code == 404


# ---- admin page ----


def test_admin_adds_a_message_that_the_user_sees(
    admin_client, student_browser, db, admin
):
    response = post(
        admin_client,
        "/mtas-admin/notifications/add",
        {"title": "New exercise", "body": "See Downloads."},
    )
    item = db.query(Notification).one()
    assert response.headers["location"] == f"/mtas-admin/notifications/{item.itid}"
    assert (item.kind, item.created_by, item.user_id) == ("message", admin.itid, None)
    assert item.shown_at is not None and item.hidden is False
    assert "New exercise" in student_browser.get("/account").text

    page = admin_client.get("/mtas-admin/notifications").text
    assert "New exercise" in page and "All users" in page
    entry = db.query(AdminActions).filter_by(action="notification_added").one()
    assert entry.details == "New exercise"


def test_admin_hides_edits_and_deletes(admin_client, student_browser, db, student):
    item = add_message(db)
    notifications.mark_read(db, student, item.itid)
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/hide")
    assert "Exam on Friday" not in student_browser.get("/account").text
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/hide")
    assert "Exam on Friday" in student_browser.get("/account").text

    post(
        admin_client,
        f"/mtas-admin/notifications/{item.itid}/edit",
        {"title": "Exam on Monday", "body": "Changed"},
    )
    db.expire_all()
    assert (item.title, item.body) == ("Exam on Monday", "Changed")

    post(admin_client, f"/mtas-admin/notifications/{item.itid}/delete")
    db.expire_all()
    assert db.query(Notification).count() == 0
    assert db.query(NotificationRead).count() == 0
    actions = {row.action for row in db.query(AdminActions)}
    assert {
        "notification_hidden",
        "notification_shown",
        "notification_changed",
        "notification_deleted",
    } <= actions


def test_admin_edits_and_hides_in_the_list(admin_client, student_browser, db):
    item = add_message(db)
    page = admin_client.get("/mtas-admin/notifications").text
    edit_link = f'href="/mtas-admin/notifications/{item.itid}" title="Change the text'
    assert edit_link in page and "Edit</a>" in page
    assert "<details" not in page[page.index("notifications-table") :]
    response = post(
        admin_client,
        f"/mtas-admin/notifications/{item.itid}/edit",
        {"title": "Exam on Monday", "back": "list"},
    )
    assert response.headers["location"] == (
        f"/mtas-admin/notifications#notification-{item.itid}"
    )
    response = post(
        admin_client, f"/mtas-admin/notifications/{item.itid}/hide", {"back": "list"}
    )
    assert response.headers["location"].startswith("/mtas-admin/notifications#")
    assert "Exam on Monday" not in student_browser.get("/account").text


def test_admin_sees_how_many_users_read_it(admin_client, db, student, admin):
    item = add_message(db)
    notifications.mark_read(db, student, item.itid)
    page = admin_client.get("/mtas-admin/notifications").text
    # admin and student are the users of the course
    assert '<td class="num">1 / 2</td>' in page
    assert (
        "Read by 1 user."
        in admin_client.get(f"/mtas-admin/notifications/{item.itid}").text
    )


def test_users_cannot_open_the_admin_page(student_client, db):
    item = add_message(db)
    assert student_client.get("/mtas-admin/notifications").status_code == 403
    response = post(student_client, f"/mtas-admin/notifications/{item.itid}/delete")
    assert response.status_code == 403


# ---- e-mail: first a test to the admin, then to the users ----


def test_email_without_a_test(admin_client, db, mails, student):
    item = add_message(db)
    page = admin_client.get(f"/mtas-admin/notifications/{item.itid}").text
    assert '<fieldset class="plain">' in page and "(optional)" in page

    post(
        admin_client,
        f"/mtas-admin/notifications/{item.itid}/email-users",
        {"audience": "all"},
    )
    assert sorted(mail["to"] for mail in mails) == [ADMIN_EMAIL, STUDENT_EMAIL]
    assert db.query(BackgroundTask).one().status == "done"


def test_email_test_then_all_users(admin_client, db, mails, student):
    item = add_message(db, body="Room A1\nhttps://example.org/room")
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/email-test")
    assert [mail["to"] for mail in mails] == [ADMIN_EMAIL]
    assert mails[0]["subject"] == 'Notification about "Exam on Friday"'
    # only the text of the admin: no extra link to the page Account
    assert mails[0]["content"] == (
        "Dear student,\n\nRoom A1\nhttps://example.org/room\n\n"
        "Best regards,\nCourse Team\n"
    )
    db.expire_all()
    assert item.email_test_to == ADMIN_EMAIL

    post(
        admin_client,
        f"/mtas-admin/notifications/{item.itid}/email-users",
        {"audience": "all"},
    )
    assert sorted(mail["to"] for mail in mails[1:]) == [ADMIN_EMAIL, STUDENT_EMAIL]
    task = db.query(BackgroundTask).one()
    assert (task.kind, task.status) == ("notification:email", "done")
    assert "was sent to 2 users" in task.message
    db.expire_all()
    assert item.emailed_count == 2 and item.emailed_at is not None


def test_email_to_selected_users(admin_client, db, mails, student):
    other = add_user(db, email="other@uni.example", number=7)
    item = add_message(db)
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/email-test")
    response = admin_client.post(
        f"/mtas-admin/notifications/{item.itid}/email-users",
        data={
            "csrf_token": _token(admin_client),
            "audience": "selected",
            "user_id": [str(student.itid), str(other.itid)],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert sorted(mail["to"] for mail in mails[1:]) == [
        "other@uni.example",
        STUDENT_EMAIL,
    ]


def test_selected_without_users_sends_nothing(admin_client, db, mails):
    item = add_message(db)
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/email-test")
    post(
        admin_client,
        f"/mtas-admin/notifications/{item.itid}/email-users",
        {"audience": "selected"},
    )
    assert len(mails) == 1  # only the test
    assert (
        "Choose at least one user."
        in admin_client.get(f"/mtas-admin/notifications/{item.itid}").text
    )


def test_an_edit_needs_a_new_test(admin_client, db, mails):
    item = add_message(db)
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/email-test")
    post(
        admin_client,
        f"/mtas-admin/notifications/{item.itid}/edit",
        {"title": "Exam moved"},
    )
    db.expire_all()
    assert item.email_test_at is None


def test_failed_test_email(admin_client, db, monkeypatch):
    monkeypatch.setattr(notifications, "send_email", lambda *args, **kw: False)
    item = add_message(db)
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/email-test")
    db.expire_all()
    assert item.email_test_at is None
    assert (
        "The test e-mail was not sent."
        in admin_client.get(f"/mtas-admin/notifications/{item.itid}").text
    )


def _token(client) -> str:
    from tests.conftest import csrf_token

    return csrf_token(client, "/about")


# ---- automatic notifications ----


def test_event_gives_only_one_notification(db, student):
    assert notifications.notify(db, "page", "A", event_key="x") is True
    assert notifications.notify(db, "page", "A again", event_key="x") is False
    db.commit()
    assert db.query(Notification).count() == 1


def test_switched_off_events_give_nothing(db, use_settings):
    use_settings(NOTIFICATIONS_AUTO="survey")
    assert notifications.notify(db, "page", "A") is False
    assert notifications.notify(db, "survey", "B") is True


def test_automatic_notifications_wait_for_the_admin(admin_client, student_browser, db):
    notifications.notify(db, "page", "New page: Downloads", event_key="a")
    notifications.notify(db, "page", "New page: Reviews", event_key="b")
    db.commit()
    assert "New page" not in student_browser.get("/account").text
    page = admin_client.get("/mtas-admin/notifications").text
    assert "2 automatic notifications wait" in page
    # the admin menu shows the number too
    assert 'title="Waiting to be shown">2</span>' in page

    item = db.query(Notification).filter_by(event_key="a").one()
    post(admin_client, f"/mtas-admin/notifications/{item.itid}/hide")
    text = student_browser.get("/account").text
    assert "New page: Downloads" in text and "New page: Reviews" not in text

    post(admin_client, "/mtas-admin/notifications/show-waiting")
    assert "New page: Reviews" in student_browser.get("/account").text
    assert (
        "automatic notifications wait"
        not in admin_client.get("/mtas-admin/notifications").text
    )


def test_admin_deletes_the_waiting_ones(admin_client, db):
    notifications.notify(db, "page", "A", event_key="a")
    shown = add_message(db, title="Shown")
    db.commit()
    post(admin_client, "/mtas-admin/notifications/delete-waiting")
    assert [row.title for row in db.query(Notification)] == [shown.title]


def show_all(db):
    for item in db.query(Notification):
        notifications.show(item)
    db.commit()


def test_service_shown_tells_the_users_with_an_account(admin_client, db, student):
    other = add_user(db, email="other@uni.example", number=7)
    db.add(
        MetabaseService(
            user_id=student.itid,
            metabase_login="x",
            metabase_password="pw",
            metabase_docker_port=3001,
        )
    )
    db.commit()
    change_ui_visibility_settings(db, "metabase", False)
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "metabase", "visible": "true"},
    )
    rows = db.query(Notification).all()
    assert [(r.kind, r.title, r.audience, r.hidden) for r in rows] == [
        ("service", "New service: Metabase", "service:metabase", True)
    ]
    assert rows[0].body == (
        "`Metabase` service is now accessible on the page **Services**."
    )
    assert "waits at Notifications" in admin_client.get("/mtas-admin/visibility").text
    assert not notifications.for_user(db, student)
    show_all(db)
    assert len(notifications.for_user(db, student)) == 1
    assert not notifications.for_user(db, other)

    # hidden and shown again on the same day: no second notification
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "metabase", "visible": "false"},
    )
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "metabase", "visible": "true"},
    )
    assert db.query(Notification).count() == 1


def test_already_visible_gives_nothing(admin_client, db, student):
    add_postgresql(db, student)
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "postgresql", "visible": "true"},
    )
    assert db.query(Notification).count() == 0


def test_dataset_shown_tells_the_users_with_postgresql(admin_client, db, student):
    add_postgresql(db, student)
    change_ui_visibility_settings(db, "importers_flights", False)
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "importers_flights", "visible": "true"},
    )
    row = db.query(Notification).one()
    assert (row.kind, row.title, row.audience) == (
        "dataset",
        "New dataset: Flights",
        "service:postgresql",
    )


def test_page_shown_tells_all_users(admin_client, student_browser, db):
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "downloads", "visible": "true"},
    )
    row = db.query(Notification).one()
    assert (row.kind, row.title, row.user_id) == ("page", "New page: Downloads", None)
    assert "New page: Downloads" not in student_browser.get("/account").text
    post(admin_client, f"/mtas-admin/notifications/{row.itid}/hide")
    assert "New page: Downloads" in student_browser.get("/account").text


def test_self_start_switch_gives_nothing(admin_client, db):
    change_ui_visibility_settings(db, "metabase_self_managment", False)
    post(
        admin_client,
        "/mtas-admin/visibility",
        {"ui_key": "metabase_self_managment", "visible": "true"},
    )
    assert db.query(Notification).count() == 0


def make_download(db, visible=True) -> Downloads:
    item = Downloads(
        title="Task 3",
        description="PDF",
        original_name="t.pdf",
        stored_name="x.pdf",
        size_bytes=1,
        sha256="0" * 64,
        content_type="application/pdf",
        visible=visible,
    )
    db.add(item)
    db.commit()
    return item


def test_new_download_on_a_visible_page(db):
    item = make_download(db)
    assert notifications.download_added(db, item, page_visible=False) is False
    assert notifications.download_added(db, make_download(db, False), True) is False
    assert notifications.download_added(db, item, page_visible=True) is True
    assert notifications.download_added(db, item, page_visible=True) is False
    db.commit()
    row = db.query(Notification).one()
    assert (row.kind, row.title, row.body) == (
        "download",
        "New download: Task 3",
        "PDF",
    )


def test_survey_given_tells_its_users(admin_client, db, student, admin, mails):
    other = add_user(db, email="other@uni.example", number=7)
    link = SimpleNamespace(
        survey_id=5, url="https://x/s/5", auth_url=None, status="not_started"
    )
    surveys._store_link(db, student.itid, "Feedback", link)
    db.commit()
    surveys._store_link(db, student.itid, "Feedback", link)
    surveys._store_link(db, admin.itid, "Feedback", link)
    db.commit()
    row = db.query(Notification).one()
    assert (row.kind, row.title, row.audience) == (
        "survey",
        "New survey: Feedback",
        "survey:5",
    )
    show_all(db)
    assert notifications.for_user(db, student) and notifications.for_user(db, admin)
    assert not notifications.for_user(db, other)

    # the e-mail goes only to the users of the survey
    post(admin_client, f"/mtas-admin/notifications/{row.itid}/email-test")
    post(
        admin_client,
        f"/mtas-admin/notifications/{row.itid}/email-users",
        {"audience": "all"},
    )
    assert sorted(mail["to"] for mail in mails[1:]) == [ADMIN_EMAIL, STUDENT_EMAIL]


def test_new_version_once(db):
    assert REAL_NEW_VERSION(db) is True
    assert REAL_NEW_VERSION(db) is False
    row = db.query(Notification).one()
    assert row.kind == "version" and row.hidden


def test_version_notification_at_the_start(app, db, monkeypatch):
    monkeypatch.setattr(notifications, "new_version", REAL_NEW_VERSION)
    with TestClient(app):
        pass
    assert db.query(Notification).filter_by(kind="version").count() == 1


# ---- Markdown, and the record of the e-mails ----


def test_markdown_in_the_notification_and_the_email(
    student_client, admin_client, db, mails
):
    item = add_message(
        db,
        body="**Room A1**, see https://example.org/plan\n<script>x</script>"
        "\n[bad](javascript:alert(1))",
    )
    text = student_client.get("/account").text
    assert "<strong>Room A1</strong>" in text
    assert '<a href="https://example.org/plan" rel="noopener" target="_blank">' in text
    assert "<script>x</script>" not in text and "&lt;script&gt;" in text
    assert "javascript:" not in text

    post(admin_client, f"/mtas-admin/notifications/{item.itid}/email-test")
    # plain text: the Markdown as written; HTML: rendered
    assert mails[0]["content"].startswith("Dear student,\n\n**Room A1**")
    assert "<strong>Room A1</strong>" in mails[0]["html"]


def test_markdown_in_descriptions(admin_client, db):
    from app.markdown_text import render_inline

    assert str(render_inline("A *PDF* file")) == "A <em>PDF</em> file"
    item = make_download(db)
    item.description = "See **page 2**"
    db.commit()
    page = admin_client.get("/mtas-admin/downloads").text
    assert "See <strong>page 2</strong>" in page


def test_email_goes_once_and_failed_ones_again(admin_client, db, mails, student, admin):
    item = add_message(db)
    mails.fail = {STUDENT_EMAIL}
    url = f"/mtas-admin/notifications/{item.itid}/email-users"
    post(admin_client, url, {"audience": "missing"})
    assert [mail["to"] for mail in mails] == [ADMIN_EMAIL]
    # one connection for all e-mails of a task
    assert mails.connections == 1
    state = notifications.email_state(db, item.itid)
    assert state["sent"] == 1
    assert [(row.email, row.status) for row in state["failed"]] == [
        (STUDENT_EMAIL, "failed")
    ]
    page = admin_client.get(f"/mtas-admin/notifications/{item.itid}").text
    assert "1 not sent" in page and "who did not get it yet (1)" in page

    # a second click: only the failed one, not the admin again
    mails.fail = set()
    post(admin_client, url, {"audience": "missing"})
    assert [mail["to"] for mail in mails] == [ADMIN_EMAIL, STUDENT_EMAIL]
    db.expire_all()
    assert item.emailed_count == 2

    # nothing left: no task
    tasks = db.query(BackgroundTask).count()
    post(admin_client, url, {"audience": "missing"})
    assert db.query(BackgroundTask).count() == tasks
    assert (
        "All users got this e-mail already."
        in admin_client.get(url.rsplit("/", 1)[0]).text
    )

    # "all again" sends to everyone
    post(admin_client, url, {"audience": "all"})
    assert len(mails) == 4


def test_email_being_sent_is_not_sent_twice(db, mails, student):
    item = add_message(db)
    assert notifications._claim(db, item.itid, student, again=True) is True
    # another task (or a second click) cannot take it while it is being sent
    assert notifications._claim(db, item.itid, student, again=True) is False
    row = db.query(NotificationEmail).one()
    row.updated_at = utc_now() - notifications.SENDING_TIMEOUT - timedelta(minutes=1)
    db.commit()
    # a task that stopped long ago: the e-mail is free again
    assert notifications._claim(db, item.itid, student, again=False) is True


def test_audiences_need_one_query(db, student):
    from sqlalchemy import event

    add_postgresql(db, student)
    queries = []
    engine = db.get_bind()
    listener = lambda *args: queries.append(args[2])  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        first = notifications.audiences_of(db, student)
        again = notifications.audiences_of(db, student)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert first == again == ["service:postgresql"]
    assert len(queries) == 1


def test_mailer_uses_one_connection_and_reconnects(monkeypatch, use_settings):
    import smtplib

    from app import emails
    from app.config import get_settings

    servers = []

    class FakeServer:
        def __init__(self):
            self.sent = []
            servers.append(self)

        def send_message(self, msg):
            # the first server closes after one e-mail
            if self is servers[0] and self.sent:
                raise smtplib.SMTPServerDisconnected("closed")
            if msg["To"] == "refused@uni.example":
                raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no")})
            self.sent.append(msg["To"])

        def quit(self):
            pass

    monkeypatch.setattr(emails, "connect", lambda settings: FakeServer())
    with emails.Mailer(get_settings()) as mailer:
        assert mailer.send("a@uni.example", "S", "**T**", "<b>T</b>") is None
        assert mailer.send("b@uni.example", "S", "T") is None
        assert mailer.send("refused@uni.example", "S", "T") is not None
        assert mailer.send("c@uni.example", "S", "T") is None
    assert [server.sent for server in servers] == [
        ["a@uni.example"],
        ["b@uni.example", "c@uni.example"],
    ]


def test_email_has_a_text_and_an_html_part():
    from app.emails import build_email

    msg = build_email("a@uni.example", "S", "**T**", None, html="<p><b>T</b></p>")
    assert [part.get_content_type() for part in msg.iter_parts()] == [
        "text/plain",
        "text/html",
    ]


# ---- subject and e-mail history ----


def test_admin_changes_the_subject(admin_client, db, mails, student):
    item = add_message(db)
    url = f"/mtas-admin/notifications/{item.itid}"
    assert 'value="Notification about &#34;Exam on Friday&#34;"' in admin_client.get(
        url
    ).text.replace("&quot;", "&#34;")

    post(admin_client, f"{url}/email-test")
    post(admin_client, f"{url}/email-subject", {"subject": "  Exam   moved "})
    db.expire_all()
    assert item.email_subject == "Exam moved"
    # a new subject needs a new test
    assert item.email_test_at is None
    post(admin_client, f"{url}/email-users", {"audience": "all"})
    assert {mail["subject"] for mail in mails[1:]} == {"Exam moved"}

    # empty: back to the default, which follows the title
    post(admin_client, f"{url}/email-subject", {"subject": ""})
    post(admin_client, f"{url}/edit", {"title": "Exam on Monday"})
    db.expire_all()
    assert item.email_subject is None
    assert notifications.email_subject(item) == 'Notification about "Exam on Monday"'


def test_email_history(admin_client, db, mails, student, admin):
    item = add_message(db, body="**Room A1**")
    url = f"/mtas-admin/notifications/{item.itid}"
    mails.fail = {STUDENT_EMAIL}
    post(admin_client, f"{url}/email-test")
    post(admin_client, f"{url}/email-users", {"audience": "all"})

    test, users = db.query(EmailBatch).order_by(EmailBatch.itid).all()
    assert (test.kind, users.kind) == ("test", "users")
    assert users.subject == '[MTA-SYSTEM] Notification about "Exam on Friday"'
    assert "**Room A1**" in users.body and users.finished_at is not None
    rows = {
        row.email: (row.status, row.error)
        for row in db.query(EmailBatchItem).filter_by(batch_id=users.itid)
    }
    assert rows == {
        ADMIN_EMAIL: ("sent", None),
        STUDENT_EMAIL: ("failed", "the server refused the address"),
    }

    rules = admin_client.get("/mtas-admin/notifications").text
    assert "<h2>Notification rules</h2>" in rules
    assert "<th data-sort>Kind</th>" in rules
    assert '<td class="small nowrap">Message</td>' in rules
    assert rules.count('<span class="badge success">on</span>') == 6
    assert 'href="/mtas-admin/notifications/emails"' in rules

    page = admin_client.get("/mtas-admin/notifications/emails").text
    assert page.count('href="/mtas-admin/notifications/emails/') == 2
    assert "to the users" in page and '<span class="badge danger">1</span>' in page
    assert "E-mail history of this notification (2)" in admin_client.get(url).text

    page = admin_client.get(f"/mtas-admin/notifications/emails/{users.itid}").text
    assert "<strong>Room A1</strong>" in page
    assert STUDENT_EMAIL in page and "the server refused the address" in page

    # the history stays when the notification is deleted
    post(admin_client, f"{url}/delete")
    db.expire_all()
    assert db.query(EmailBatch).count() == 2
    assert users.notification_id is None
    page = admin_client.get(f"/mtas-admin/notifications/emails/{users.itid}").text
    assert "The notification was deleted." in page


def test_users_cannot_open_the_email_history(student_client):
    response = student_client.get(
        "/mtas-admin/notifications/emails", follow_redirects=False
    )
    assert response.status_code in (302, 303, 403, 404)
