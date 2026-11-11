import logging
import smtplib
from email.message import EmailMessage

from app.config import Settings

logger = logging.getLogger(__name__)

REGISTRATION_TEXT = """Dear student,

this is the confirmation of your registration.

Please, use the following link to get access to credentials and settings of services, which are hosted on the online platform:

{link}

You can also access the online platform with your E-MAIL and this PIN: {pin}

The link above could be used to check, which services are available to you and how to use them.

Good luck!

Best regards,
VLBA Course Team
"""


def email_content(link: str, pin: str) -> str:
    return REGISTRATION_TEXT.format(link=link, pin=pin)


def build_email(to_email: str, subject: str, content: str, sender: str | None):
    msg = EmailMessage()
    msg["Subject"] = subject or "No Subject"
    msg["From"] = sender or ""
    msg["To"] = to_email
    msg.set_content(content or "No body")
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


def send_email(to_email: str, subject: str, content: str, settings: Settings) -> bool:
    """Sends an e-mail through the SMTP server of the settings. Returns True if it was sent."""

    msg = build_email(to_email, subject, content, settings.mail_default_sender)
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
