import copy
import traceback
import uuid

import docker
from flask import abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from markupsafe import Markup, escape
from sqlalchemy import and_, or_
from sqlalchemy.sql.expression import delete, false

from .. import settings as settings
from ..extensions import db
from ..main.mhelpers import container_status_to_html, email_to_name, get_user_data
from ..main.services_helpers import metabase_user, openrefine_user
from ..models import MetabaseService, OpenRefineService, Users
from ..utils.uhelpers import to_json_sqla
from . import admin
from .ahelpers import get_users_data, has_admin_rights


@admin.route("/viewServicesMetabase", methods=["GET"])
@login_required
def viewServicesMetabase():
    """Handles admin view of a service - metabase"""

    if not has_admin_rights():
        abort(403)

    info_message = request.values.get("message")

    course_security_code = current_app.config["COURSE_SECURITY_CODE"]
    users_data = get_users_data(course_security_code)

    containers_to_check = []
    for user in users_data:
        mb_service = (
            db.session.query(MetabaseService)
            .filter(
                and_(
                    MetabaseService.user_id == user["itid"],
                    MetabaseService.deleted == False,
                )
            )
            .all()
        )
        user["service_created_status"] = None
        if len(mb_service) == 0:
            user["service_created_status"] = "not exists"
        elif len(mb_service) > 1:
            user["service_created_status"] = "too many services"
        else:
            user["service_created_status"] = f"{mb_service[0].created}"
        user["service_container_name"] = get_docker_service_name_metabase(user["itid"])
        containers_to_check.append(user["service_container_name"])

    # statuses to all containers at once
    containers_status_lst = get_docker_status_batch(containers_to_check)
    for user in users_data:
        for container in containers_status_lst:
            if user["service_container_name"] == container["container_name"]:
                user["service_container_status"] = Markup(container["status_as_html"])

    return render_template(
        "admin/admin_services_metabase_ui.html",
        usersData=users_data,
        message=info_message,
        menu="admin",
    )


@admin.route("/viewServicesOpenRefine", methods=["GET"])
@login_required
def viewServicesOpenRefine():
    """Handles admin view of a service - OpenRefine"""

    if not has_admin_rights():
        abort(403)

    info_message = request.values.get("message")

    course_security_code = current_app.config["COURSE_SECURITY_CODE"]
    users_data = get_users_data(course_security_code)

    containers_to_check = []
    for user in users_data:
        or_service = (
            db.session.query(OpenRefineService)
            .filter(
                and_(
                    OpenRefineService.user_id == user["itid"],
                    OpenRefineService.deleted == False,
                )
            )
            .all()
        )
        user["service_created_status"] = None
        if len(or_service) == 0:
            user["service_created_status"] = "not exists"
        elif len(or_service) > 1:
            user["service_created_status"] = "too many services"
        else:
            user["service_created_status"] = f"{or_service[0].created}"
        user["service_container_name"] = get_docker_service_name_openrefine(
            user["itid"]
        )
        containers_to_check.append(user["service_container_name"])

    # statuses to all containers at once
    containers_status_lst = get_docker_status_batch(containers_to_check)
    for user in users_data:
        for container in containers_status_lst:
            if user["service_container_name"] == container["container_name"]:
                user["service_container_status"] = Markup(container["status_as_html"])

    return render_template(
        "admin/admin_services_openrefine_ui.html",
        usersData=users_data,
        message=info_message,
        menu="admin",
    )


@admin.route("/startService", methods=["GET"])
@login_required
def startService():
    """Handles admin view of a service"""

    if not has_admin_rights():
        abort(403)

    info_message = None

    user_id = request.values.get("user_id", None)
    service_name = request.values.get("service_name", None)

    if user_id is not None:
        user_id = escape(user_id)
    if service_name is not None:
        service_name = escape(service_name)

    if not check_supported_services(service_name):
        return redirect(
            url_for(
                "admin.viewAdmin", message=f"Service is not supported: {service_name}"
            )
        )

    try:
        perform_action_on_docker(
            user_id=user_id, service_name=service_name, action="START"
        )
    except Exception as ex:
        current_app.logger.error(ex, exc_info=True)
        info_message = f"[x] Error: {str(ex)}"
        return redirect(url_for("admin.viewAdmin", message=info_message))

    return handle_service_redirect(
        service_name, message=f"The service should be started by now: {service_name}"
    )


@admin.route("/stopService", methods=["GET"])
@login_required
def stopService():
    """Handles admin view of a service"""

    if not has_admin_rights():
        abort(403)

    info_message = None

    user_id = request.values.get("user_id", None)
    service_name = request.values.get("service_name", None)

    if user_id is not None:
        user_id = escape(user_id)

    if service_name is not None:
        service_name = escape(service_name)

    if not check_supported_services(service_name):
        return redirect(
            url_for(
                "admin.viewAdmin", message=f"Service is not supported: {service_name}"
            )
        )

    try:
        perform_action_on_docker(
            user_id=user_id, service_name=service_name, action="STOP"
        )
    except Exception as ex:
        current_app.logger.error(ex, exc_info=True)
        info_message = f"[x] Error: {str(ex)}"
        return redirect(url_for("admin.viewAdmin", message=info_message))

    return handle_service_redirect(
        service_name, message=f"The service should be stopped by now: {service_name}"
    )


@admin.route("createServicesMetabase", methods=["GET"])
@login_required
def createServicesMetabase():
    """Handles admin view of a service - metabase"""

    if not has_admin_rights():
        abort(403)

    user_id = request.values.get("user_id", None)
    if user_id is not None:
        user_id = escape(user_id)
    else:
        return redirect(
            url_for(".viewServicesMetabase", message="User ID should be provided")
        )

    try:
        user = db.session.query(Users).filter(Users.itid == user_id).all()

        if len(user) != 1:
            return redirect(
                url_for(".viewServicesMetabase", message="Too many users found")
            )

        user_data = get_user_data(user[0].url_hash)
        if "postgresql_service" not in user_data:
            return redirect(
                url_for(
                    ".viewServicesMetabase", message="No PostgreSQL service was found."
                )
            )

        postgresql_user = user_data["postgresql_service"]["postgresql_user"]
        postgresql_password = user_data["postgresql_service"]["postgresql_password"]
        user_internal_email = user_data["users"]["internal_email"]

        mb_docker_port = int(postgresql_user[-2:]) + settings.METABASE_PORT_OFFSET
        current_app.logger.info(f"metabase docker port should be: {mb_docker_port}")
        handle_old_docker_containers_metabase(user_id, mb_docker_port)

        is_created = metabase_user(
            user_id=user_id,
            email=user_internal_email,
            password=postgresql_password,
            docker_port=mb_docker_port,
        )
        if not is_created:
            info_message = (
                f"Could not create metabase service for the user. ID: {user_id}"
            )

    except Exception as ex:
        current_app.logger.error(ex, exc_info=True)
        info_message = f"[x] Error: {str(ex)}"
        return redirect(url_for(".viewServicesMetabase", message=info_message))

    return redirect(
        url_for(
            ".viewServicesMetabase",
        )
    )

    return redirect(
        url_for(
            ".viewServicesMetabase",
            message=f"The service should be created by now. ID: {user_id}",
        )
    )


@admin.route("/createServicesOpenRefine", methods=["GET"])
@login_required
def createServicesOpenRefine():
    """Handles admin view of a service - OpenRefine"""

    if not has_admin_rights():
        abort(403)

    user_id = request.values.get("user_id", None)
    if user_id is not None:
        user_id = escape(user_id)
    else:
        return redirect(
            url_for(".viewServicesOpenRefine", message="User ID should be provided")
        )

    try:
        user = db.session.query(Users).filter(Users.itid == user_id).all()

        if len(user) != 1:
            return redirect(
                url_for(".viewServicesOpenRefine", message="Too many users found")
            )

        user_data = get_user_data(user[0].url_hash)
        if "postgresql_service" not in user_data:
            return redirect(
                url_for(
                    ".viewServicesOpenRefine",
                    message="No PostgreSQL service was found.",
                )
            )

        postgresql_user = user_data["postgresql_service"]["postgresql_user"]
        postgresql_password = user_data["postgresql_service"]["postgresql_password"]
        openrefine_username = "{0}_{1}".format(
            settings.OPENREFINE_USER_PREFIX, postgresql_user[-2:]
        )
        openrefine_docker_port = (
            int(postgresql_user[-2:]) + settings.OPENREFINE_PORT_OFFSET
        )
        current_app.logger.info(
            f"openrefine docker port should be: {openrefine_docker_port}"
        )
        handle_old_docker_containers_openrefine(user_id, openrefine_docker_port)
        openrefine_user(
            user_id=user_id,
            user_name=openrefine_username,
            password=postgresql_password,
            docker_port=openrefine_docker_port,
            force_create=True,
        )

    except Exception as ex:
        current_app.logger.error(ex, exc_info=True)
        info_message = f"[x] Error: {str(ex)}"
        return redirect(url_for(".viewServicesOpenRefine", message=info_message))

    return redirect(
        url_for(
            ".viewServicesOpenRefine", message="The service should be created by now"
        )
    )


def handle_old_docker_containers_openrefine(user_id: int, openrefine_docker_port: int):
    op_docker_name = f"openrefine-{openrefine_docker_port}"
    rename_docker_container(op_docker_name, f"{op_docker_name}-{uuid.uuid1()}")
    db.session.query(OpenRefineService).filter(
        OpenRefineService.user_id == user_id
    ).update({"deleted": True, "created": False})
    db.session.commit()


def handle_old_docker_containers_metabase(user_id: int, openrefine_docker_port: int):
    mb_docker_name = f"metabase-{openrefine_docker_port}"
    rename_docker_container(mb_docker_name, f"{mb_docker_name}-{uuid.uuid1()}")
    db.session.query(MetabaseService).filter(MetabaseService.user_id == user_id).update(
        {"deleted": True, "created": False}
    )
    db.session.commit()


def rename_docker_container(old_name: str, new_name: str):
    try:
        client = docker.from_env()
        lst_containers = client.containers.list(all=True)
        for container in lst_containers:
            if container.name == old_name:
                container.rename(new_name)
                container.stop()
                current_app.logger.debug(
                    f'Change name of the contains from "{old_name}" to "{new_name}"'
                )
    except ImportError as ex:
        current_app.logger.error(ex, exc_info=True)
        return False
    except OSError as ex:
        current_app.logger.error(ex, exc_info=True)
        return False

    return True


def get_docker_service_name_openrefine(user_id: int):
    user_data_or = (
        db.session.query(OpenRefineService)
        .filter(
            and_(
                OpenRefineService.user_id == user_id, OpenRefineService.deleted == False
            )
        )
        .all()
    )

    if len(user_data_or) != 1:
        return None
    openrefine_docker_name = f"openrefine-{user_data_or[0].openrefine_docker_port}"

    return openrefine_docker_name


def get_docker_service_name_metabase(user_id: int):
    user_data_or = (
        db.session.query(MetabaseService)
        .filter(
            and_(MetabaseService.user_id == user_id, MetabaseService.deleted == False)
        )
        .all()
    )

    if len(user_data_or) != 1:
        return None
    metabase_docker_name = f"metabase-{user_data_or[0].metabase_docker_port}"

    return metabase_docker_name


def get_docker_status(container_name: str) -> str:
    container_status = None
    try:
        client = docker.from_env()
        lst_containers = client.containers.list(all=True)
        for container in lst_containers:
            if container.name == container_name:
                container_status = container_status_to_html(container.status)
                break
    except ImportError as ex:
        current_app.logger.error(f"No module installed: docker. Exception {ex}")
    except OSError as ex:
        current_app.logger.error(f"No access to docker. Exception {ex}")
    except Exception as ex:
        current_app.logger.error(
            f"Another docker relevant exception. Exception {ex}", exc_info=True
        )

    return container_status


def get_docker_status_batch(container_name_lst: list) -> list:
    container_status_lst = []
    try:
        client = docker.from_env()
        lst_containers = client.containers.list(all=True)
        for container in lst_containers:
            if container.name in container_name_lst:
                container_status_lst.append(
                    {
                        "container_name": container.name,
                        "status_as_html": container_status_to_html(container.status),
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

    return container_status_lst


def perform_action_on_docker(user_id: int, service_name: str, action: str) -> str:

    info_message = None
    try:
        service_docker_name = None
        if service_name == "metabase":
            service_docker_name = get_docker_service_name_metabase(user_id)
        elif service_name == "openrefine":
            service_docker_name = get_docker_service_name_openrefine(user_id)

        if service_docker_name is None:
            info_message = "Could not find a respected service"
        else:
            if run_action_on_docker_container(service_docker_name, action):
                info_message = "The service should be stopped by now"
            else:
                info_message = "The service WAS NOT stopped"
    except Exception as ex:
        current_app.logger.error(ex, exc_info=True)
        info_message = f"[x] Error: {str(ex)}"

    return info_message


def run_action_on_docker_container(container_name: str, action: str) -> bool:
    allowed_actions = ["STOP", "START"]
    if action.upper() not in allowed_actions:
        current_app.logger.error(
            f'Action on docker is not supported. Docker: "{container_name}", action: "{action}"'
        )
        return False
    try:
        client = docker.from_env()
        lst_containers = client.containers.list(all=True)
        for container in lst_containers:
            if container.name == container_name:
                if action.upper() == "STOP":
                    container.stop()
                    current_app.logger.debug(
                        f'Container was stopped: "{container_name}"'
                    )
                if action.upper() == "START":
                    container.start()
                    current_app.logger.debug(
                        f'Container was stopped: "{container_name}"'
                    )
    except ImportError as ex:
        current_app.logger.error(ex, exc_info=True)
        return False
    except OSError as ex:
        current_app.logger.error(ex, exc_info=True)
        return False

    return True


def handle_service_redirect(service_name, message):

    if service_name == "openrefine":
        return redirect(url_for(".viewServicesOpenRefine", message=message))

    if service_name == "metabase":
        return redirect(url_for(".viewServicesMetabase", message=message))

    return redirect(
        url_for("admin.viewAdmin", message="Unknown service for the redirect")
    )


def check_supported_services(service_name: str) -> bool:
    supported_services = ["openrefine", "metabase"]
    if service_name in supported_services:
        return True
    return False
