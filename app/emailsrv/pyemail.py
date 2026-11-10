#!/usr/bin/env python

import smtplib
import traceback
from datetime import datetime
from email.message import EmailMessage


def print_msg(msg, logger=None):
    """Prints a message into console and log (if needed)"""

    if logger is not None:
        logger.info(msg)
    print(f"{datetime.now()}  {__name__}  {msg}")


def build_email(to_email, subject=None, content=None, settings=None):
    """Forms an e-mail and returns it as a result."""

    # msg = MIMEMultipart()
    msg = EmailMessage()

    if to_email is None:
        return None

    if subject is None:
        subject = "No Subject"
    if content is None:
        content = "No body"

    msg["Subject"] = subject
    msg["From"] = settings["MAIL_DEFAULT_SENDER"]
    msg["To"] = to_email

    msg.set_content(content)
    print_msg("[i] an email was formed")

    return msg


def send_email(to_email, subject, content, settings=None, verbose=False):
    """Send the email via your own SMTP server."""

    msg = build_email(
        to_email=to_email, subject=subject, content=content, settings=settings
    )

    try:
        s = smtplib.SMTP(settings["MAIL_SERVER"], settings["MAIL_PORT"])
        print_msg("[i] connected to the SMTP")
        s.ehlo()
        s.starttls()
        if verbose:
            print_msg("[i] TLS started")
        s.login(settings["MAIL_USERNAME"], settings["MAIL_PASSWORD"])
        if verbose:
            print_msg("[i] login done")
        s.sendmail(settings["MAIL_DEFAULT_SENDER"], to_email, msg.as_string())
        print_msg("[i] e-mail was sent")
    except Exception as e:
        print_msg("[e] Error: unable to send email")
        print(traceback.format_exc())


def email_content(link, pin):

    email_content = """Dear student,

this is the confirmation of your registration.

Please, use the following link to get access to credentials and settings of services, which are hosted on the online platform:

{link}

You can also access the online platform with your E-MAIL and this PIN: {pin}

The link above could be used to check, which services are available to you and how to use them.

Good luck!

Best regards,
VLBA Course Team
"""
    return email_content.format(link=link, pin=pin)
