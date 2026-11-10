import json
import traceback

from email_validator import EmailNotValidError, validate_email
from flask import current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from markupsafe import Markup, escape

from .. import settings as settings
from ..admin.ahelpers import has_admin_rights
from ..main.shared_helpers import ui_visibility_settings
from ..utils.captcha import generate_captcha
from ..utils.security import make_hash, verify_hash
from ..utils.uhelpers import to_json_sqla
from . import main
from .exercises_helpers import (
    PART_BONUS,
    PART_REVIEW,
    get_exercises,
    get_latest_review,
    get_user_bonus_points,
    render_review_content,
)
from .mhelpers import (
    construct_db_uri_for_user,
    get_user_data,
    resend_email,
    start_docker_container,
    user_containers_status,
)
from .newuser_helpers import (
    assign_available_account_to_user,
    check_if_user_exists,
    is_email_in_allowed_fqdn_list,
    register_new_routine,
    send_confirmation_email,
)


# add constant value to all views
@main.context_processor
def inject_user():
    return dict(
        courseName=current_app.config["COURSE_NAME_TITLE"],
        serviceVisibility=ui_visibility_settings(),
        adminAccount=has_admin_rights(),
    )


@main.route("/")
@main.route("/index")
def index():
    return render_template("index.html")


@main.route("/about")
def viewDescription():
    return render_template("about.html")


@main.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        error = None

        inputEmailField = request.values.get("inputEmailField", None)
        if inputEmailField is not None:
            inputEmailField = escape(inputEmailField)

        inputCodeField = request.values.get("inputCodeField", None)
        if inputCodeField is not None:
            inputCodeField = escape(inputCodeField)

        inputCaptchaField = request.values.get("inputCaptchaField", None)
        if inputCaptchaField is not None:
            inputCaptchaField = escape(inputCaptchaField)

        inputCaptchaGUIDField = request.values.get("inputCaptchaGUIDField", None)
        if inputCaptchaGUIDField is not None:
            inputCaptchaGUIDField = escape(inputCaptchaGUIDField)

        course_security_code = current_app.config["COURSE_SECURITY_CODE"]

        if inputCodeField is not None:
            inputCodeField = inputCodeField.upper()

        if course_security_code is not None:
            course_security_code = course_security_code.upper()

        new_user_email = inputEmailField.strip().lower()
        current_app.logger.info(
            "E-mail received for the registration: {0}".format(new_user_email)
        )

        if new_user_email is not None and len(new_user_email) > 0:
            try:
                validate_email(
                    new_user_email, check_deliverability=False, allow_smtputf8=False
                )
            except EmailNotValidError as ex:
                error = "[x] E-mail is not valid for the registration: {0}".format(ex)
                current_app.logger.warning(error)
        else:
            error = "Provide an e-mail for the registration"

        if error is None:
            if not (
                is_email_in_allowed_fqdn_list(
                    new_user_email, current_app.config["ALLOWED_FQDN_FOR_EMAILS"]
                )
            ):
                error = "Please, use the e-mail of your organization"

        if error is None:
            if not (inputCodeField == course_security_code):
                error = "Please, provide the correct special code"

        if error is None:
            if not (
                verify_hash(
                    inputCaptchaField,
                    inputCaptchaGUIDField,
                    current_app.config["HASH_KEY_HIDDEN"],
                )
            ):
                error = "Please, provide the correct captcha"

        if error is None:
            if not (
                verify_hash(
                    inputCaptchaField,
                    inputCaptchaGUIDField,
                    current_app.config["HASH_KEY_HIDDEN"],
                )
            ):
                error = "Please, provide the correct captcha"

        if error is None:
            was_registered = False
            try:
                is_exist, user_data = check_if_user_exists(new_user_email)
                if is_exist:
                    was_registered = True
                    resend_email(user_data, settings.BASE_URL)

                if not was_registered:
                    was_assigned = assign_available_account_to_user(new_user_email)
                    if not was_assigned:
                        was_registered = register_new_routine(new_user_email)
                    if was_registered:
                        send_confirmation_email(new_user_email)

            except Exception as ex:
                current_app.logger.warning(f"Exception at the registration: {ex}")
                current_app.logger.error(traceback.format_exc())
                return render_template("register/registerException.html")

            if is_exist and was_registered:
                return render_template("register/registerAlreadyExists.html")

            if not is_exist and was_registered:
                return render_template("register/registerSuccess.html")

            if not is_exist and not was_registered:
                return render_template("register/registerTryAgain.html", error=error)

        return render_template("register/registerTryAgain.html", error=error)

    if request.method == "GET":
        captcha_txt, captcha_png = generate_captcha(add_noise=True)
        return render_template(
            "register/register.html",
            captchaImageAsBase64=captcha_png,
            inputCaptchaGUIDField=make_hash(
                captcha_txt, current_app.config["HASH_KEY_HIDDEN"]
            ),
        )


@main.route("/services", methods=["GET"])
@login_required
def viewServices():
    """Handles view of an available services"""

    # from .. extensions import rq_worker
    # task = rq_worker.enqueue(rq_test_function, 5)

    info_message = request.values.get("message")
    if info_message is not None:
        info_message = escape(info_message)

    cmd = request.values.get("cmd")
    if cmd is not None:
        cmd = escape(cmd)

    cmd_start_mb, cmd_start_or, cmd_start_nifi, cmd_start_wp = (
        "startMetabase",
        "startOpenrefine",
        "startNiFi",
        "startWordpress",
    )

    user_data = get_user_data(current_user.get_id())

    if user_data:

        # start docker container, if a command supplied
        if cmd is not None:
            if cmd.upper() == cmd_start_mb.upper():
                info_message = start_docker_container(
                    user_data["metabase_service"], service_type="metabase"
                )
            if cmd.upper() == cmd_start_or.upper():
                info_message = start_docker_container(
                    user_data["openrefine_service"], service_type="openrefine"
                )
            if cmd.upper() == cmd_start_nifi.upper():
                info_message = start_docker_container(
                    user_data["nifi_service"], service_type="nifi"
                )
            if cmd.upper() == cmd_start_wp.upper():
                info_message = start_docker_container(
                    user_data["wordpress_service"], service_type="wordpress"
                )

            return redirect(f"services?message={info_message}")

        pg_user_data = None
        superset_sqlalchermy_uri = None
        if "postgresql_service" in user_data:
            pg_user_data = user_data["postgresql_service"]
            superset_sqlalchermy_uri = construct_db_uri_for_user(pg_user_data)

        container_statuses = user_containers_status(user_data)

        response_data = {}

        # postgresql
        if pg_user_data is not None:
            response_data["postgresql_service"] = {}
            response_data["postgresql_service"]["server"] = settings.POSTGRESQL_SERVER
            response_data["postgresql_service"][
                "port"
            ] = settings.POSTGRESQL_SERVER_PORT
            response_data["postgresql_service"]["db"] = pg_user_data["postgresql_db"]
            response_data["postgresql_service"]["user"] = pg_user_data[
                "postgresql_user"
            ]
            response_data["postgresql_service"]["password"] = pg_user_data[
                "postgresql_password"
            ]

        # pgAdmin4
        if "pgadmin4_service" in user_data:
            pgadmin4_user_data = user_data["pgadmin4_service"]
            response_data["pgadmin4_service"] = {}
            response_data["pgadmin4_service"]["url"] = settings.PGADMIN4_URL
            response_data["pgadmin4_service"]["login"] = pgadmin4_user_data[
                "pgadmin4_user"
            ]
            response_data["pgadmin4_service"]["password"] = pgadmin4_user_data[
                "pgadmin4_password"
            ]

        # # superset
        # if 'superset_service' in user_data:
        #     superset_user_data = user_data['superset_service']
        #     response_data['superset_service'] = {}
        #     response_data['superset_service']['url'] = settings.SUPERSET_URL
        #     response_data['superset_service']['user'] = superset_user_data['superset_user']
        #     response_data['superset_service']['password'] = superset_user_data['superset_password']
        #     response_data['superset_service']['SQLAlchemyURI']  = superset_sqlalchermy_uri

        # JupyterHub
        if "jupyterhub_service" in user_data:
            jh_user_data = user_data["jupyterhub_service"]
            response_data["jupyterhub_service"] = {}
            response_data["jupyterhub_service"]["url"] = settings.JUPYTERHUB_URL
            response_data["jupyterhub_service"]["user"] = jh_user_data[
                "jupyterhub_user"
            ]
            response_data["jupyterhub_service"]["password"] = jh_user_data[
                "jupyterhub_password"
            ]

        # Metabase
        if "metabase_service" in user_data:
            mb_user_data = user_data["metabase_service"]
            metabase_url_tpl = "https://{backend}/metabase/{dockerPort}/"
            metabase_url = metabase_url_tpl.format(
                backend=settings.BASE_BACKEND,
                dockerPort=mb_user_data["metabase_docker_port"],
            )
            response_data["metabase_service"] = {}
            response_data["metabase_service"]["email"] = user_data["users"][
                "internal_email"
            ]
            response_data["metabase_service"]["password"] = mb_user_data[
                "metabase_password"
            ]
            response_data["metabase_service"]["url"] = metabase_url
            response_data["metabase_service"]["startCmd"] = cmd_start_mb
            response_data["metabase_service"]["containerStatus"] = Markup(
                container_statuses["metabase"]
            )

        # OpenRefine
        if "openrefine_service" in user_data:
            or_user_data = user_data["openrefine_service"]
            openrefine_url_tpl = "https://{backend}/openrefine/{dockerPort}/"
            openrefine_url = openrefine_url_tpl.format(
                backend=settings.BASE_BACKEND,
                dockerPort=or_user_data["openrefine_docker_port"],
            )
            response_data["openrefine_service"] = {}
            response_data["openrefine_service"]["user"] = or_user_data[
                "openrefine_user"
            ]
            response_data["openrefine_service"]["password"] = or_user_data[
                "openrefine_password"
            ]
            response_data["openrefine_service"]["url"] = openrefine_url
            response_data["openrefine_service"]["startCmd"] = cmd_start_or
            response_data["openrefine_service"]["containerStatus"] = Markup(
                container_statuses["openrefine"]
            )

        # Nifi
        if "nifi_service" in user_data:
            nifi_user_data = user_data["nifi_service"]
            nifi_url_tpl = "https://{backend}/nifi/{dockerPort}/nifi/"
            nifi_url = nifi_url_tpl.format(
                backend=settings.BASE_BACKEND,
                dockerPort=nifi_user_data["nifi_docker_port"],
            )

            nifi_db_connection_url = None
            if pg_user_data is not None:
                nifi_db_connection_url = f"jdbc:postgresql://{settings.BASE_BACKEND}:5432/{pg_user_data['postgresql_db']}"

            response_data["nifi_service"] = {}
            response_data["nifi_service"]["user"] = nifi_user_data["nifi_user"]
            response_data["nifi_service"]["password"] = nifi_user_data["nifi_password"]
            response_data["nifi_service"]["url"] = nifi_url
            response_data["nifi_service"]["startCmd"] = cmd_start_nifi
            response_data["nifi_service"]["containerStatus"] = Markup(
                container_statuses["nifi"]
            )
            response_data["nifi_service"]["DBConnectionURL"] = nifi_db_connection_url

        # mariadb_service
        if "mariadb_service" in user_data:
            mariadb_user_data = user_data["mariadb_service"]
            response_data["mariadb_service"] = {}
            response_data["mariadb_service"]["server"] = settings.MARIADB_SERVER
            response_data["mariadb_service"]["port"] = settings.MARIADB_SERVER_PORT
            response_data["mariadb_service"]["db"] = mariadb_user_data["mariadb_db"]
            response_data["mariadb_service"]["user"] = mariadb_user_data["mariadb_user"]
            response_data["mariadb_service"]["password"] = mariadb_user_data[
                "mariadb_password"
            ]

        # wordpress_service
        if "wordpress_service" in user_data:
            wordpress_user_data = user_data["wordpress_service"]
            wordpress_url_tpl = "https://{backend}/wordpress/{dockerPort}/"

            wordpress_url = wordpress_url_tpl.format(
                backend=settings.BASE_BACKEND,
                dockerPort=wordpress_user_data["wordpress_docker_port"],
            )

            wordpress_admin_suffix = "wp-admin"
            wordpress_url_admin = f"{wordpress_url}{wordpress_admin_suffix}/"

            response_data["wordpress_service"] = {}
            response_data["wordpress_service"]["login"] = wordpress_user_data[
                "wordpress_login"
            ]
            response_data["wordpress_service"]["password"] = wordpress_user_data[
                "wordpress_password"
            ]
            response_data["wordpress_service"]["url"] = wordpress_url
            response_data["wordpress_service"]["urlAdmin"] = wordpress_url_admin
            response_data["wordpress_service"]["startCmd"] = cmd_start_wp
            response_data["wordpress_service"]["containerStatus"] = Markup(
                container_statuses["wordpress"]
            )

        return render_template(
            "services.html", data=response_data, message=info_message
        )
    else:
        return render_template("services.html", message=info_message)


@main.route("/importer", methods=["GET"])
@login_required
def viewImporter():
    """Handles importer actions"""

    dataset = escape(request.values.get("dataset", None))
    datasets_available = ["flights", "airbnb", "adventureworks"]
    current_app.logger.info(f"Dataset for importer: {dataset}")
    info_message = f"Adding dataset: {dataset}"

    if dataset is not None:
        if dataset not in datasets_available:
            return redirect(url_for("main.viewServices", message="[x] No such dataset"))

        user_data = get_user_data(current_user.get_id())

        if user_data is None:
            return redirect(url_for("main.viewServices"))

        pg_user_data = user_data["postgresql_service"]
        postgresql_db_uri = construct_db_uri_for_user(pg_user_data)

        # flights
        if dataset == datasets_available[0]:
            current_app.logger.info(
                f"Importing {dataset} for user {current_user.get_id()}"
            )
            from ..importers.flights import importer_flights as flights

            try:
                flights.run_import(db_connect_uri=postgresql_db_uri)
            except Exception as ex:
                current_app.logger.error(ex, exc_info=True)
                info_message = f"[x] Error: {str(ex)}"
            current_app.logger.info(
                f"Imported {dataset} for user {current_user.get_id()}"
            )

        # airbnb
        if dataset == datasets_available[1]:
            current_app.logger.info(
                f"Importing {dataset} for user {current_user.get_id()}"
            )
            from ..importers.airbnb import importer_airbnb_csv as airbnb

            try:
                airbnb.run_import(db_connect_uri=postgresql_db_uri)
            except Exception as ex:
                current_app.logger.error(ex, exc_info=True)
                info_message = f"[x] Error: {str(ex)}"
            current_app.logger.info(
                f"Imported {dataset} for user {current_user.get_id()}"
            )

        # adventureworks
        if dataset == datasets_available[2]:
            current_app.logger.info(
                f"Importing {dataset} for user {current_user.get_id()}"
            )
            from ..importers.adventureworks_custom import (
                importer_adventureworks_custom as adventureworks,
            )

            try:
                adventureworks.run_import(postgresql_db_uri)
            except Exception as ex:
                current_app.logger.error(ex, exc_info=True)
                info_message = f"[x] Error: {str(ex)}"
            current_app.logger.info(
                f"Imported {dataset} for user {current_user.get_id()}"
            )

    return redirect(url_for("main.viewServices", message=info_message))


@main.route("/reviews", methods=["GET"])
@login_required
def viewReviews():
    """Handles view of reviews on exercises (if any)"""

    info_message = request.values.get("message")
    if info_message is not None:
        info_message = escape(info_message)

    exercises_lst = []
    user_data = get_user_data(current_user.get_id())
    if user_data:
        exercises = get_exercises(part=PART_REVIEW, only_visible=True)
        for exercise in exercises.values():
            review = get_latest_review(user_data["users"]["itid"], exercise["itid"])
            if review is not None:
                review_json = to_json_sqla(review)
                exercise["content"] = render_review_content(review_json)
                exercise["submitted"] = review.submitted
                exercise["reviewed"] = review.reviewed
                exercise["visible"] = review.visible
            exercises_lst.append(exercise)

    return render_template(
        "reviewExercises.html", message=info_message, exercises=exercises_lst
    )


@main.route("/bonus", methods=["GET"])
@login_required
def viewBonus():
    """Handles view of bonus (if any)"""

    info_message = request.values.get("message")
    if info_message is not None:
        info_message = escape(info_message)
    user_data = get_user_data(current_user.get_id())

    bonus_points = {}
    if user_data:
        exercises = get_exercises(part=PART_BONUS)
        bonus_points["bonuses"], bonus_points["bonus_total"] = get_user_bonus_points(
            exercises, user_data["users"]["itid"]
        )

    return render_template(
        "bonus.html", message=info_message, userBonusPoints=bonus_points
    )


# def rq_test_function(delay:int):
#     import os
#     import uuid
#     import time

#     time.sleep(delay)
#     print(f'Delay: {delay}')
#     fname = f'{str(uuid.uuid4())}.txt'
#     with open(fname, "w") as _file:
#         _file.write("... ping ...")
