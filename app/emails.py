import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# in front of each subject, and the name of the sender
SUBJECT_PREFIX = "[MTA-SYSTEM]"
SENDER_NAME = "modular teaching assistance system"

# plain-text e-mails (app/templates/emails): the same greeting and signature
_texts = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(enabled_extensions=("html",)),
    keep_trailing_newline=True,
)


def render_text(name: str, **values) -> str:
    """The text of app/templates/emails/<name>.txt"""

    values.setdefault("signature", get_settings().mail_signature)
    return _texts.get_template(f"emails/{name}.txt").render(**values)


def email_content(link: str, pin: str) -> str:
    return render_text("registration", link=link, pin=pin)


def build_email(
    to_email: str,
    subject: str,
    content: str,
    sender: str | None,
    html: str | None = None,
):
    """content: the plain text. html: optional second part (e-mail programs show it)"""

    msg = EmailMessage()
    msg["Subject"] = f"{SUBJECT_PREFIX} {subject or 'No Subject'}"
    address = parseaddr(sender or "")[1]
    msg["From"] = formataddr((SENDER_NAME, address)) if address else ""
    msg["To"] = to_email
    msg.set_content(content or "No body")
    if html:
        msg.add_alternative(
            f'<!doctype html><html><body style="font-family: sans-serif">{html}'
            "</body></html>",
            subtype="html",
        )
    return msg


def connect(settings: Settings) -> smtplib.SMTP:
    """Opens a connection to the SMTP server of the settings (STARTTLS and login)"""

    server = smtplib.SMTP(
        settings.mail_server, settings.mail_port, timeout=settings.mail_timeout_sec
    )
    try:
        server.ehlo()
        server.starttls()
        if settings.mail_username:
            password = settings.mail_password
            server.login(
                settings.mail_username, password.get_secret_value() if password else ""
            )
    except Exception:
        server.close()
        raise
    return server


def describe_error(error: Exception, settings: Settings) -> str:
    """Short text about an SMTP error, with what to check"""

    address = f"{settings.mail_server}:{settings.mail_port}"
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return f"SMTP server {address} refused the login: check MAIL_USERNAME and MAIL_PASSWORD"
    if isinstance(error, smtplib.SMTPException):
        return f"SMTP server {address} answered with an error: {error}"
    return (
        f"Cannot connect to the SMTP server {address} ({error}). Check MAIL_SERVER and "
        "MAIL_PORT, and that this computer can reach the server (network, VPN, firewall)"
    )


def send_email(
    to_email: str,
    subject: str,
    content: str,
    settings: Settings,
    html: str | None = None,
) -> bool:
    """Sends an e-mail through the SMTP server of the settings. Returns True if it was sent."""

    msg = build_email(to_email, subject, content, settings.mail_default_sender, html)
    try:
        with connect(settings) as server:
            server.send_message(msg)
    except OSError as error:
        # smtplib.SMTPException is an OSError too
        logger.error(
            "E-mail to %s was not sent. %s", to_email, describe_error(error, settings)
        )
        return False
    except Exception:
        logger.exception("Unable to send the e-mail to %s", to_email)
        return False
    logger.info("E-mail was sent to %s", to_email)
    return True


class Mailer:
    """Many e-mails over one SMTP connection (opened at the first e-mail).

    with Mailer(settings) as mailer: error = mailer.send(...)  # None: sent
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.server = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        if self.server is not None:
            try:
                self.server.quit()
            except (OSError, smtplib.SMTPException):
                self.server.close()
            self.server = None

    def send(
        self, to_email: str, subject: str, content: str, html: str | None = None
    ) -> str | None:
        """Returns None if the e-mail was sent, else a short error text"""

        msg = build_email(
            to_email, subject, content, self.settings.mail_default_sender, html
        )
        # a second try on a new connection: the server may have closed the old one
        for attempt in (1, 2):
            try:
                if self.server is None:
                    self.server = connect(self.settings)
                self.server.send_message(msg)
                logger.info("E-mail was sent to %s", to_email)
                return None
            except smtplib.SMTPRecipientsRefused as error:
                logger.error("E-mail to %s was refused: %s", to_email, error)
                return "the server refused the address"
            except OSError as error:
                self.close()
                if attempt == 2:
                    text = describe_error(error, self.settings)
                    logger.error("E-mail to %s was not sent. %s", to_email, text)
                    return text
        return "not sent"
