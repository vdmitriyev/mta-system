import os
import traceback
import uuid
from subprocess import PIPE, Popen, TimeoutExpired

import requests
from flask import abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from markupsafe import Markup, escape
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError

from .. import settings as settings
from ..extensions import db
from ..main.mhelpers import (
    container_status_to_html,
    email_to_name,
    email_to_tokens,
    get_user_data,
)
from ..main.shared_helpers import change_ui_visibility_settings, ui_visibility_settings
from ..models import Users
from ..utils.uhelpers import to_json_sqla
from . import admin
from .ahelpers import has_admin_rights

ADMIN_UI_URL = "adminView"
DEFAULT_MAX_USER_ACCOUNTS_TO_CREATE = 5


# add constant value to all views
@admin.context_processor
def inject_user():
    return dict(
        courseName=current_app.config["COURSE_NAME_TITLE"],
        serviceVisibility=ui_visibility_settings(),
        adminAccount=has_admin_rights(),
        maxAccountsToCreate=os.environ.get("MAX_USER_ACCOUNTS_TO_CREATE")
        or DEFAULT_MAX_USER_ACCOUNTS_TO_CREATE,
    )


@admin.route("/", methods=["GET"])
@admin.route("/index", methods=["GET"])
@login_required
def viewAdminIndex():
    """Admin interface - redirection"""
    return redirect(url_for(".viewAdmin"))


@admin.route("/adminView", methods=["GET"])
@login_required
def viewAdmin():
    """Handles admin view"""

    current_app.logger.info(f"Try to access admin UI. User id: {current_user.get_id()}")

    if not has_admin_rights():
        current_app.logger.warning(
            f"User has no admin privileges. User id: {current_user.get_id()}"
        )
        abort(403)

    info_message = request.values.get("message")
    if info_message is not None:
        info_message = escape(info_message)

    cmd_mb_generate_bash = "generateBashMetabase"
    cmd_or_generate_bash = "generateBashOpenrefine"
    cmd_nifi_generate_bash = "generateBashNifi"
    cmd_jhub_generate_bash = "generateBashJupyterhub"

    cmd = escape(request.values.get("cmd", None))
    jh_user = escape(request.values.get("jh_user", None))
    current_app.logger.debug(f"Command received (admin): {cmd}")

    cmd_output = admin_generate_cmds(
        cmd,
        cmd_mb_generate_bash,
        cmd_or_generate_bash,
        cmd_nifi_generate_bash,
        cmd_jhub_generate_bash,
        jh_user,
    )

    return render_template(
        "admin/admin_main_ui.html",
        urlMBGenerateBash=f'{url_for("admin.viewAdmin")}?cmd={cmd_mb_generate_bash}',
        urlORGenerateBash=f"{ADMIN_UI_URL}?cmd={cmd_or_generate_bash}",
        urlNifiGenerateBash=f"{ADMIN_UI_URL}?cmd={cmd_nifi_generate_bash}",
        urlJHubGenerateBash=f"{ADMIN_UI_URL}?cmd={cmd_jhub_generate_bash}",
        cmdOutput=Markup(cmd_output),
        message=info_message,
        menu="admin",
    )


@admin.route("/adminMonitoring", methods=["GET"])
@login_required
def adminMonitoring():
    """Handles admin view for monitoring"""

    current_app.logger.info(f"Try to access admin UI. User id: {current_user.get_id()}")

    if not has_admin_rights():
        current_app.logger.warning(
            f"User has no admin privileges. User id: {current_user.get_id()}"
        )
        abort(403)

    server_summary = admin_server_summary()
    containers = get_containers_infos()

    return render_template(
        "admin/admin_monitoring.html",
        containers=containers,
        serverSummary=server_summary,
        menu="admin",
    )


@admin.route("/accessCheckBasicAuth", methods=["GET"])
@login_required
def accessCheckBasicAuth():
    """Check access"""

    current_app.logger.info(f"Try to access admin UI. User id: {current_user.get_id()}")

    if not has_admin_rights():
        current_app.logger.warning(
            f"User has no admin privileges. User id: {current_user.get_id()}"
        )
        abort(403)

    course_security_code = current_app.config["COURSE_SECURITY_CODE"]
    users = (
        db.session.query(Users)
        .filter(and_(Users.deleted == False, Users.course_code == course_security_code))
        .order_by(Users.email.asc())
        .all()
    )

    basic_auth_checks = []
    for user in users:
        user_data = get_user_data(user.url_hash)
        check_entry = {}
        check_entry["name"] = email_to_name(user_data["users"]["email"])
        check_entry["courseCode"] = user_data["users"]["course_code"]

        openrefine_data = user_data.get("openrefine_service")
        if openrefine_data is None:
            check_entry["openRefineUser"] = "-"
            check_entry["orCheckVerdict"] = "NO SERVICE"
            basic_auth_checks.append(check_entry)
            continue

        check_entry["openRefineUser"] = openrefine_data["openrefine_user"]
        docker_port = openrefine_data["openrefine_docker_port"]
        if docker_port is None:
            check_entry["orCheckVerdict"] = "NO PORT"
            basic_auth_checks.append(check_entry)
            continue

        username_basic_auth = openrefine_data["openrefine_user"]
        password_basic_auth = openrefine_data["openrefine_password"]
        response_status = "UNKNOWN"
        try:
            openrefine_url = (
                f"https://{settings.BASE_BACKEND}/openrefine/{docker_port}/"
            )
            response = requests.get(
                openrefine_url,
                auth=(username_basic_auth, password_basic_auth),
                verify=False,
                timeout=4,
            )
            if response is None:
                response_status = "UNEXPECTED"
            response_status = response.status_code
        except requests.exceptions.Timeout:
            response_status = "TIMEOUT"
        except requests.exceptions.ConnectionError as e:
            response_status = "DOWN"
            current_app.logger.error(traceback.format_exc())
        except Exception as e:
            response_status = "EXCEPTION"
            current_app.logger.error(traceback.format_exc())

        check_entry["orCheckVerdict"] = response_status
        basic_auth_checks.append(check_entry)

    return render_template(
        "admin/admin_check_basic_auth.html",
        basicAuthChecks=basic_auth_checks,
        menu="admin",
    )


@admin.route("/generateUserAccounts", methods=["GET"])
@login_required
def generateUserAccounts():
    """Generates user accounts and services"""

    import time

    from ..main.views import register_new_routine

    current_app.logger.info(f"Try to access admin UI. User id: {current_user.get_id()}")

    if not has_admin_rights():
        current_app.logger.warning(
            f"User has no admin privileges. User id: {current_user.get_id()}"
        )
        abort(403)

    MAX_USER_ACCOUNTS_TO_CREATE = int(
        os.environ.get("MAX_USER_ACCOUNTS_TO_CREATE")
        or DEFAULT_MAX_USER_ACCOUNTS_TO_CREATE
    )
    current_app.logger.info(
        f"Start pre-generating user accounts: {MAX_USER_ACCOUNTS_TO_CREATE}"
    )
    info_message = None
    for index in range(MAX_USER_ACCOUNTS_TO_CREATE):
        generated_email = f"tmp.generated{index}_{str(uuid.uuid1())[:4]}@localhost.lc"
        register_new_routine(new_user_email=generated_email, do_assign_user=False)
        current_app.logger.info(
            f"Create services for the non-assigned user with the email: {generated_email}"
        )
        time.sleep(3)

    info_message = (
        f"New user accounts should be generated: {MAX_USER_ACCOUNTS_TO_CREATE}"
    )

    return redirect(url_for(".viewAdmin", message=info_message))


@admin.route("/viewConfigs", methods=["GET"])
@login_required
def adminViewConfigs():
    """Shows flask config files"""

    current_app.logger.info(f"Try to access admin UI. User id: {current_user.get_id()}")

    if not has_admin_rights():
        current_app.logger.warning(
            f"User has no admin privileges. User id: {current_user.get_id()}"
        )
        abort(403)

    info_message = request.values.get("message")
    if info_message is not None:
        info_message = escape(info_message)

    env_configs = []
    exclude_keywords = [
        "SECRET_KEY",
        "PASSWORD",
        "HASH_KEY_HIDDEN",
        "HASH_KEY_LINKS",
        "SQLALCHEMY_DATABASE_URI",
    ]
    for item, value in current_app.config.items():
        exclude = False
        for to_exclude in exclude_keywords:
            if to_exclude in item.upper():
                exclude = True
        if not exclude:
            env_configs.append({"key": item, "value": value})

            server_env_configs = {}

    DEFAULT_CATEGORY = "_DEFAULT_CATEGORY"
    server_env_configs[DEFAULT_CATEGORY] = []
    for item in env_configs:
        if len(item["key"].split("_")) > 1:
            category = item["key"].split("_")[0]
            if category not in server_env_configs:
                server_env_configs[category] = []
            server_env_configs[category].append(item)
        else:
            server_env_configs[DEFAULT_CATEGORY].append(item)

    for key in list(server_env_configs):
        if len(server_env_configs[key]) == 1:
            server_env_configs[DEFAULT_CATEGORY].append(server_env_configs[key][0])
            server_env_configs.pop(key)

    settings_config = []
    try:
        params_excluded = [
            "PY_PLANTSIM_LAUNCHER_ROOT",
            "PY_PLANTSIM_LAUNCHER_NAME",
            "PLANTSIM_WORKING_DIR",
        ]
        for param_name in dir(settings):
            if param_name.isupper() and param_name not in params_excluded:
                settings_config.append(
                    {"key": param_name, "value": getattr(settings, param_name)}
                )
    except Exception as ex:
        current_app.logger.error(
            f"Settings look up error. Exception {ex}", exc_info=True
        )

    server_env_configs["_SETTINGS"] = settings_config
    server_env_configs = {k: server_env_configs[k] for k in sorted(server_env_configs)}

    return render_template(
        "admin/admin_configs.html", envConfigs=server_env_configs, message=info_message
    )


@admin.route("/viewUIVisibilitySettings", methods=["GET"])
@login_required
def adminViewUIVisibilitySettings():
    """Shows UI Visibility Settings"""

    current_app.logger.info(f"Try to access admin UI. User id: {current_user.get_id()}")

    if not has_admin_rights():
        current_app.logger.warning(
            f"User has no admin privileges. User id: {current_user.get_id()}"
        )
        abort(403)

    info_message = request.values.get("message")
    if info_message is not None:
        info_message = escape(info_message)

    ui_visibility = ui_visibility_settings()

    return render_template(
        "admin/admin_ui_visibility_settings.html",
        uiVisibility=ui_visibility,
        message=info_message,
    )


@admin.route("/changeUIVisibilitySettings")
@login_required
def adminViewChangeUIVisibilitySettings():
    """Changes UI Visibility Settings"""

    ui_key = escape(request.values.get("uiKey", None))
    target = escape(request.values.get("target", None))
    info_message = "No proper values were provided"

    if ui_key is not None or target is not None:
        try:
            if target.upper() in ["ON", "OFF"]:
                _visibility = True if target.upper() == "ON" else False
                change_ui_visibility_settings(ui_key, _visibility)
                info_message = f"Visibility was changed: {ui_key}"
            else:
                info_message = f"Unrecognized value of the target parameter"
        except SQLAlchemyError:
            current_app.logger.error(traceback.format_exc())
            info_message = f"Exception during the visibility change request:&nbsp;<b>wrong parameters</b>"
        except Exception as ex:
            current_app.logger.error(traceback.format_exc())
            info_message = (
                f"Exception during the visibility change request: <b>{escape(ex)}</b>"
            )

    return redirect(
        url_for("admin.adminViewUIVisibilitySettings", message=info_message)
    )


def admin_generate_cmds(
    cmd,
    cmd_mb_generate_bash,
    cmd_or_generate_bash,
    cmd_nifi_generate_bash,
    cmd_jhub_generate_bash,
    jh_user,
):
    """Generates CMDs for admin UI"""

    cmd_output = ""

    # metabase bash commands
    if cmd == cmd_mb_generate_bash:

        bash_commands = []
        bash_cmd_tpl = " python metabase_api.py -dp {docker_port} -f {fname} -l {lname} -e {email} -p {password}"
        results = (
            db.session.query(Users)
            .filter(Users.metabase_docker_port == None)
            .order_by(Users.created_at.asc())
            .all()
        )
        for user in results:
            tokens = email_to_tokens(user.email)
            # need to identify docker port here
            _user_name = str(user.postgresql_db)
            new_docker_port = (
                int(_user_name[_user_name.rfind("_") + 1 :])
                + settings.METABASE_PORT_OFFSET
            )

            new_cmd = bash_cmd_tpl.format(
                docker_port=new_docker_port,
                fname=tokens[0].title(),
                lname=tokens[1].title(),
                email=user.email,
                password=user.metabase_password,
            )
            bash_commands.append(new_cmd)

        cmd_output = "-- <i>metabase commands</i> </br></br>"
        cmd_output = cmd_output + "</br>".join(bash_commands)

    # openrefine bash commands
    if cmd == cmd_or_generate_bash:
        cmd_output = generate_bash_cmds_for_openrefine()

    # nifi bash commands
    if cmd == cmd_nifi_generate_bash:

        bash_commands = []
        bash_cmd_tpl = (
            " python nifi_api.py -dp {docker_port} -u {user_name} -p {password}"
        )
        results = (
            db.session.query(Users)
            .filter(Users.nifi_docker_port == None)
            .order_by(Users.created_at.asc())
            .all()
        )
        for user in results:

            # need to identify docker port here
            _user_name = str(user.nifi_user)
            new_docker_port = (
                int(_user_name[_user_name.rfind("_") + 1 :]) + settings.NIFI_PORT_OFFSET
            )

            new_cmd = bash_cmd_tpl.format(
                docker_port=new_docker_port,
                user_name=_user_name,
                password=user.nifi_password,
            )
            bash_commands.append(new_cmd)

        cmd_output = "-- <i>nifi commands</i> </br></br>"
        cmd_output = cmd_output + "</br>".join(bash_commands)

    # jupyterhub bash commands
    if cmd == cmd_jhub_generate_bash:

        bash_commands = []
        bash_cmd_tpl = """# should be executed on VM, where the docker is running under SUDO / or has access to docker
docker exec jupyterhub-2020 /bin/sh -c 'adduser --disabled-password --gecos "" {user}'
docker exec jupyterhub-2020 /bin/bash -c "echo '{user}:{password}'|chpasswd"
docker exec jupyterhub-2020 /bin/bash -c "mkdir -p /home/{user}/notebooks/"
docker exec jupyterhub-2020 /bin/bash -c "cp -r /srv/jupyterhub/datasets/sentiment-data /home/{user}/notebooks/"
docker exec jupyterhub-2020 /bin/bash -c "chown  -R {user}:{user} /home/{user}/notebooks/"

sleep 2

"""

        results = (
            db.session.query(Users)
            .filter(Users.jupyterhub_created == False)
            .order_by(Users.created_at.asc())
            .all()
        )
        for user in results:

            if jh_user is not None:
                if jh_user == user.jupyterhub_user:
                    new_cmd = bash_cmd_tpl.format(
                        user=user.jupyterhub_user, password=user.jupyterhub_password
                    )
                    error = False
                    for cmd in new_cmd.split("\n"):
                        try:
                            if not cmd.startswith("#"):
                                current_app.logger.info(f"Execute cmd for JHub: {cmd}")
                                proc = Popen(
                                    cmd,
                                    shell=True,
                                    stdout=PIPE,
                                    stderr=PIPE,
                                    stdin=PIPE,
                                )
                                outs, errs = proc.communicate(timeout=10)
                        except TimeoutExpired as ex:
                            current_app.logger.error(
                                f"Timeout exception: {ex}", exc_info=True
                            )
                            error = True

                    if not error:
                        db.session.query(Users).filter(
                            Users.jupyterhub_user == jh_user
                        ).update({"jupyterhub_created": True})
                        db.session.commit()

                    continue

            new_cmd = bash_cmd_tpl.format(
                user=user.jupyterhub_user, password=user.jupyterhub_password
            )
            bash_commands.append(new_cmd.replace("\n", "</br>\n"))
            urlJHubСreateUser = f"{ADMIN_UI_URL}?cmd={cmd_jhub_generate_bash}&jh_user={user.jupyterhub_user}"
            bash_commands.append(
                f'<a class="btn bg-warning" type="button" name="{cmd_jhub_generate_bash}" href="{urlJHubСreateUser}">Create user: <b>{user.jupyterhub_user}</b></a>'
            )
            bash_commands.append('<hr width="80%">')

        cmd_output = "-- <i>jupyterhub commands</i> </br></br>"
        cmd_output = cmd_output + "</br>".join(bash_commands)

    return cmd_output


def generate_bash_cmds_for_openrefine() -> str:
    """_summary_

    Returns:
        str: bash commands as a text
    """

    cmd_output = ""
    bash_commands = []
    bash_cmd_tpl = (
        " python openrefine_api.py -dp {docker_port} -u {user_name} -p {password}"
    )
    results = (
        db.session.query(Users)
        .filter(Users.deleted == False)
        .order_by(Users.created_at.asc())
        .all()
    )
    for _user in results:
        user_data = get_user_data(_user.url_hash)
        if "openrefine_service" in user_data:
            or_user_data = user_data["openrefine_service"]
            # need to identify docker port here
            _user_name = str(or_user_data["user"])
            new_docker_port = (
                int(_user_name[_user_name.rfind("_") + 1 :])
                + settings.OPENREFINE_PORT_OFFSET
            )

            new_cmd = bash_cmd_tpl.format(
                docker_port=new_docker_port,
                user_name=_user_name,
                password=or_user_data["password"],
            )
            bash_commands.append(new_cmd)
        else:
            bash_commands.append(
                f'-- no data in the service table on the user: <b>{user_data["users"]["email"]}</b>'
            )

    cmd_output = "-- <i>openrefine commands</i> </br></br>"
    cmd_output = cmd_output + "</br>".join(bash_commands)

    return cmd_output


def get_containers_infos() -> list:
    """Gets information on all containers running

    Returns:
       list: a list with information about containers
    """

    containers = []
    try:
        import docker

        client = docker.from_env()
        lst_containers = client.containers.list(all=True)
        for container in lst_containers:
            container_status = container_status_to_html(container.status)
            containers.append(
                {
                    "id": container.short_id,
                    "name": container.name,
                    "image": str(container.image.tags),
                    "status": Markup(container_status),
                    "logs": Markup(format_docker_logs(container.logs(tail=20))),
                }
            )
    except ImportError as ex:
        current_app.logger.error(f"No module installed: docker. Exception {ex}")
    except OSError as ex:
        current_app.logger.error(f"No access to docker. Exception {ex}")
    except Exception as ex:
        current_app.logger.error(
            f"Another docker relevant exception. Exception {ex}", exc_info=True
        )

    return containers


def format_docker_logs(logs_in: str) -> str:
    """Formats provided logs from docker (as byte) into html

    Args:
        logs_in (str): input log stream as string

    Returns:
        str: formatted logs as HTML
    """

    try:
        return logs_in.decode().replace("\n", "<br>")
    except Exception as ex:
        current_app.logging.error(ex, exc_info=True)
        return f"Exception while formatting docker logs: {ex}"


def admin_server_summary() -> dict:
    """Gets performance metrics summary of the server.

    Returns:
        dict: metrics as a dict
    """

    summary = {}

    try:
        import docker

        client = docker.from_env()
        lst_containers = client.containers.list(all=True)
        summary["totalContainers"] = len(lst_containers)
        lst_containers_run = client.containers.list()
        summary["runningContainers"] = len(lst_containers_run)
        summary["exitedContainers"] = (
            summary["totalContainers"] - summary["runningContainers"]
        )
    except ImportError as ex:
        current_app.logger.error(f"No module installed: docker. Exception {ex}")
    except OSError as ex:
        current_app.logger.error(f"No access to docker. Exception {ex}")
    except Exception as ex:
        current_app.logger.error(
            f"Another docker relevant exception. Exception {ex}", exc_info=True
        )

    try:
        import psutil

        summary["cpuUsage"] = psutil.cpu_percent()
        # convert that object to a dictionary
        memory = dict(psutil.virtual_memory()._asdict())
        if "total" in memory:
            summary["totalMemory"] = "{:10.0f}".format(memory["total"] / (1024 * 1024))
        if "used" in memory:
            summary["usedMemory"] = "{:10.0f}".format(memory["used"] / (1024 * 1024))
        if "available" in memory:
            summary["availableMemory"] = "{:10.0f}".format(
                memory["available"] / (1024 * 1024)
            )
        if "percent" in memory:
            summary["usedMemoryPercent"] = memory["percent"]
    except ImportError as ex:
        current_app.logger.error(f"No module installed: psutil. Exception {ex}")
    except Exception as ex:
        current_app.logger.error(
            f"Other psutil relevant exception. Exception {ex}", exc_info=True
        )

    return summary
