import smtplib

from app import emails
from app.emails import build_email, email_content, send_email


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls = []
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.sent.append(message)

    def close(self):
        self.calls.append("close")


def test_email_content_has_link_and_pin():
    text = email_content(link="https://x/login?uHash=1", pin="0042")
    assert "https://x/login?uHash=1" in text
    assert "PIN: 0042" in text


def test_build_email_uses_defaults():
    message = build_email("to@x.org", None, None, None)
    assert message["Subject"] == "No Subject"
    assert message["To"] == "to@x.org"
    assert "No body" in message.get_content()


def test_send_email_with_login(use_settings, monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(emails.smtplib, "SMTP", FakeSMTP)
    settings = use_settings(
        MAIL_SERVER="smtp.x.org",
        MAIL_PORT="2525",
        MAIL_USERNAME="mailer",
        MAIL_PASSWORD="pw",
        MAIL_DEFAULT_SENDER="course@x.org",
    )

    assert send_email("to@x.org", "Registration", "Hello", settings) is True
    server = FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.x.org", 2525)
    assert server.calls == ["ehlo", "starttls", ("login", "mailer", "pw")]
    assert server.sent[0]["From"] == "course@x.org"
    assert server.sent[0]["Subject"] == "Registration"


def test_send_email_without_login(settings, monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(emails.smtplib, "SMTP", FakeSMTP)
    assert send_email("to@x.org", "S", "B", settings) is True
    assert FakeSMTP.instances[0].calls == ["ehlo", "starttls"]


def test_send_email_reports_a_failure(settings, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise smtplib.SMTPConnectError(421, "no")

    monkeypatch.setattr(emails.smtplib, "SMTP", refuse)
    assert send_email("to@x.org", "S", "B", settings) is False


def test_unreachable_server_is_logged_in_one_line(settings, monkeypatch, caplog):
    def no_route(*_args, **_kwargs):
        raise OSError(113, "No route to host")

    monkeypatch.setattr(emails.smtplib, "SMTP", no_route)
    assert send_email("to@x.org", "S", "B", settings) is False
    record = caplog.records[-1]
    assert "Cannot connect to the SMTP server localhost:587" in record.getMessage()
    assert "No route to host" in record.getMessage()
    assert record.exc_info is None


def test_wrong_login_is_named_and_the_connection_closed(
    use_settings, monkeypatch, caplog
):
    settings = use_settings(MAIL_USERNAME="mailer", MAIL_PASSWORD="wrong")

    class RefusingSMTP(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(emails.smtplib, "SMTP", RefusingSMTP)
    assert send_email("to@x.org", "S", "B", settings) is False
    assert "check MAIL_USERNAME and MAIL_PASSWORD" in caplog.text
    assert FakeSMTP.instances[-1].calls[-1] == "close"


def test_timeout_comes_from_the_settings(use_settings, monkeypatch):
    settings = use_settings(MAIL_TIMEOUT_SEC="3")
    monkeypatch.setattr(emails.smtplib, "SMTP", FakeSMTP)
    send_email("to@x.org", "S", "B", settings)
    assert FakeSMTP.instances[-1].timeout == 3
