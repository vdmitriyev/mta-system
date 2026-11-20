"""Log of the admin actions: who changed what, and for which user"""

from sqlalchemy.orm import Session

from app.models import AdminActions, Users

ACTION_LABELS = {
    "review": "Review saved",
    "bonus": "Bonus points saved",
    "extension": "Personal deadline set",
    "extension_removed": "Personal deadline removed",
    "file_deleted": "Submitted file deleted",
    "exercise": "Exercise saved",
    "user_deleted": "User deleted",
    "visibility": "Visibility changed",
    "auto_creation": "Auto creation changed",
    "download_added": "Download added",
    "download_changed": "Download changed",
    "download_moved": "Download moved",
    "download_deleted": "Download deleted",
}


def log_action(
    db: Session,
    admin: Users,
    action: str,
    user_id: int | None = None,
    exercise_code: str | None = None,
    details: str = "",
) -> None:
    """Saves the entry. Call it after the change was saved."""

    db.add(
        AdminActions(
            admin_email=admin.email,
            action=action,
            user_id=user_id,
            exercise_code=exercise_code,
            details=details or None,
        )
    )
    db.commit()


def recent_actions(db: Session, limit: int = 300, user_id: int | None = None) -> list:
    query = db.query(AdminActions)
    if user_id is not None:
        query = query.filter(AdminActions.user_id == user_id)
    return query.order_by(AdminActions.itid.desc()).limit(limit).all()
