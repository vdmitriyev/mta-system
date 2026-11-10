from flask import current_app, render_template

from .. import settings as settings
from ..admin.ahelpers import has_admin_rights
from ..main.shared_helpers import ui_visibility_settings
from . import main


@main.route("/testpage", methods=["GET"])
def viewTestPage1():
    """Test page - 1"""

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>App Test Page</title>
    </head>
    <body>
        <h1>Test, page!</h1>
    </body>
    </html>
    """

    return html_content


@main.route("/testpage2", methods=["GET"])
def viewTestPage2():
    """Test page - 2"""
    return render_template("testpage2.html")


@main.route("/testpage3", methods=["GET"])
def viewTestPage3():
    """Test page - 3"""

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>App Test Page</title>
    </head>
    <body>
        <h1>Test, page!</h1>
        <br>
        {0}
        <br>
        {1}
        <br>
        {2}
    </body>
    </html>
    """

    courseName = None  # current_app.config["COURSE_NAME_TITLE"],
    serviceVisibility = None  # ui_visibility_settings(),
    adminAccount = has_admin_rights()

    return html_content.format(courseName, serviceVisibility, adminAccount)
