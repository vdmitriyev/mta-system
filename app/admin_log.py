"""Log of the admin actions: who changed what, and for which user"""

from sqlalchemy.orm import Session

from app.models import AdminActions, Users
from app.service_settings import container_images

ACTION_LABELS = {
    "review": "Review saved",
    "bonus": "Bonus points saved",
    "extension": "Personal deadline set",
    "extension_removed": "Personal deadline removed",
    "file_deleted": "Submitted file deleted",
    "exercise": "Exercise saved",
    "user_deleted": "User deleted",
    "visibility": "Visibility changed",
    "auto_creation": "Services creation changed",
    "download_added": "Download added",
    "download_changed": "Download changed",
    "download_moved": "Download moved",
    "download_deleted": "Download deleted",
    "accounts_generated": "Accounts prepared",
    "service_created": "Service created",
    "service_start": "Container started",
    "service_stop": "Container stopped",
    "service_stop_night": "Container stopped (night)",
    "postgresql_created": "PostgreSQL database created",
    "postgresql_password": "PostgreSQL password set",  # nosec B105: a label
    "pgadmin4_login": "pgAdmin 4 login written",
    "pgadmin4_created": "pgAdmin 4 set up",
    "sqlmate_created": "sqlmate set up",
    "surveylite_created": "SurveyLite set up",
    "surveylite_login_link": "SurveyLite login link renewed",
    "survey_assigned": "Survey given",
    "survey_requirement": "Survey needed for a service",
    "notification_added": "Notification added",
    "notification_changed": "Notification changed",
    "notification_hidden": "Notification hidden",
    "notification_shown": "Notification shown again",
    "notification_deleted": "Notification deleted",
    "notification_test_email": "Notification: test e-mail",
    "notification_emailed": "Notification e-mailed to the users",
}


def log_action(
    db: Session,
    admin: Users | None,
    action: str,
    user_id: int | None = None,
    exercise_code: str | None = None,
    details: str = "",
) -> None:
    """Saves the entry. Call it after the change was saved. admin None: a job of the app."""

    db.add(
        AdminActions(
            admin_id=admin.itid if admin is not None else None,
            action=action,
            user_id=user_id,
            exercise_code=exercise_code,
            details=details or None,
        )
    )
    db.commit()


def versions(*services: str) -> str:
    """Images of the services with their versions, e.g. "metabase/metabase:v0.64-lts" """

    images = container_images()
    return ", ".join(image for service in services for image in images.get(service, []))


def recent_actions(db: Session, limit: int = 300, user_id: int | None = None) -> list:
    query = db.query(AdminActions)
    if user_id is not None:
        query = query.filter(AdminActions.user_id == user_id)
    return query.order_by(AdminActions.itid.desc()).limit(limit).all()
