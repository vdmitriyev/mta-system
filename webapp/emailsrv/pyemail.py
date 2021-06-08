#!/usr/bin/env python

import smtplib
from email.message import EmailMessage

def build_email(to_email, subject=None, content=None, settings=None):
    '''Forms an e-mail and returns it as a result.'''

    #msg = MIMEMultipart()
    msg = EmailMessage()

    if to_email is None: return None

    if subject is None: subject = 'No Subject'
    if content is None: content = 'No body'

    msg['Subject'] = subject
    msg['From'] = settings["MAIL_DEFAULT_SENDER"]
    msg['To'] = to_email

    msg.set_content(content)
    print ('[i] an email was formed')

    return msg

def send_email(to_email, subject, content, settings=None, verbose = False):
    '''Send the email via your own SMTP server.'''

    msg = build_email(to_email=to_email, subject=subject, content=content, settings=settings)

    try:
        s = smtplib.SMTP(settings["MAIL_SERVER"], settings["MAIL_PORT"])
        print ('[i] connected to the SMTP')
        s.ehlo()
        s.starttls()
        if verbose: print ('[i] TLS started')
        s.login(settings["MAIL_USERNAME"], settings["MAIL_PASSWORD"])
        if verbose: print ('[i] login done')
        s.sendmail(settings["MAIL_DEFAULT_SENDER"], to_email, msg.as_string())
        print ('[i] e-mail was sent')
    except Exception as e:
        print ('[e] Error: unable to send email')
        print ('[e] Exception: %s' % str(e))

def email_content(link, pin):

    email_content = '''Dear student,

this is the confirmation of your registration.

Please, use the following link to get personalized access to relevant services, credentials, and settings within the infrastructure: {link}

You can also access the system by using your e-mail and this PIN: {pin}

The link can be used to check, which exactly software tools and services are available to you and how to use them.

Good luck!

Best regards,
Course Team
'''
    return email_content.format(link=link, pin=pin)
