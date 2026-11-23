from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import false, func

from app.database import Base


class Users(Base):
    __tablename__ = "users"

    itid = Column(Integer, primary_key=True)
    email = Column(String(100), nullable=False)
    internal_email = Column(String(100), nullable=False)
    url_hash = Column(String(100), nullable=False, index=True)
    pin = Column(String(50), nullable=False)
    pin_hash = Column(String(100), nullable=False)
    course_code = Column(String(20))
    active = Column(Boolean, default=True, nullable=False)
    is_user_assigned = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())


class PostgreSQLService(Base):
    __tablename__ = "postgresql_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    postgresql_db = Column(String(50), nullable=False)
    postgresql_user = Column(String(50), nullable=False)
    postgresql_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class PGAdmin4Service(Base):
    __tablename__ = "pgadmin4_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    pgadmin4_user = Column(String(50), nullable=False)
    pgadmin4_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class MetabaseService(Base):
    __tablename__ = "metabase_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    metabase_login = Column(String(50), nullable=False)
    metabase_password = Column(String(50), nullable=False)
    metabase_docker_port = Column(Integer, nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class OpenRefineService(Base):
    __tablename__ = "openrefine_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    openrefine_user = Column(String(50))
    openrefine_password = Column(String(50))
    openrefine_docker_port = Column(Integer)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class JupyterHubService(Base):
    __tablename__ = "jupyterhub_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    jupyterhub_user = Column(String(50))
    jupyterhub_password = Column(String(50))
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class NiFiService(Base):
    __tablename__ = "nifi_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    nifi_user = Column(String(50))
    nifi_password = Column(String(50))
    nifi_docker_port = Column(Integer)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SupersetService(Base):
    __tablename__ = "superset_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    superset_user = Column(String(50), nullable=False)
    superset_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class MariaDBService(Base):
    __tablename__ = "mariadb_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    mariadb_db = Column(String(50), nullable=False)
    mariadb_user = Column(String(50), nullable=False)
    mariadb_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class WordpressService(Base):
    __tablename__ = "wordpress_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    wordpress_login = Column(String(50), nullable=False)
    wordpress_password = Column(String(50), nullable=False)
    wordpress_docker_port = Column(Integer, nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SqlmateService(Base):
    """Account of a user in sqlmate (SQL exercises)"""

    __tablename__ = "sqlmate_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    sqlmate_login = Column(String(100), nullable=False)
    sqlmate_pin = Column(String(50))
    # personal link that logs the user in without login and PIN
    sqlmate_login_url = Column(String(500))
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SurveyliteService(Base):
    """Anonymous participant of a user in surveylite.

    surveylite does not know who the participant is: this table is the only link.
    """

    __tablename__ = "surveylite_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    surveylite_participant_id = Column(String(64))
    surveylite_login = Column(String(100))
    surveylite_pin = Column(String(50))
    # personal login link of /me (secret as the PIN)
    surveylite_login_url = Column(String(500))
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SurveyAssignment(Base):
    """A survey of surveylite that an admin gave to a user, with the personal link"""

    __tablename__ = "survey_assignments"
    __table_args__ = (UniqueConstraint("user_id", "survey_id"),)

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=False, index=True)
    survey_id = Column(Integer, nullable=False)
    survey_title = Column(String(200))
    survey_url = Column(String(500))
    # the survey link that also logs the participant in (secret as the PIN)
    survey_auth_url = Column(String(500))
    # status in surveylite: not_started, in_progress, paused, completed, declined
    status = Column(String(20), default="not_started", nullable=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ServiceRequirement(Base):
    """A service is open for a user only after the user completed this survey"""

    __tablename__ = "service_requirements"

    service = Column(String(50), primary_key=True)
    survey_id = Column(Integer, nullable=False)
    survey_title = Column(String(200))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# Name of a service (as in SERVICES_UI) -> table with the accounts of the users
SERVICE_MODELS = {
    "postgresql": PostgreSQLService,
    "pgadmin4": PGAdmin4Service,
    "sqlmate": SqlmateService,
    "metabase": MetabaseService,
    "openrefine": OpenRefineService,
    "mariadb": MariaDBService,
    "wordpress": WordpressService,
    "surveylite": SurveyliteService,
    "nifi": NiFiService,
    "superset": SupersetService,
    "jupyterhub": JupyterHubService,
}

# Services that run in an own Docker container per user: "<service>-<port>"
CONTAINER_SERVICES = ("metabase", "openrefine", "nifi", "wordpress")


class Exercises(Base):
    """Exercise of the course. Reviews and bonus points belong to an exercise."""

    __tablename__ = "exercises"

    itid = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False, unique=True)
    name = Column(String(200))
    description = Column(String)
    year = Column(Integer)
    visible = Column(Boolean, default=True, nullable=False)
    exercise_order = Column(Integer)
    submission_deadline = Column(DateTime)
    has_review = Column(Boolean, default=True, nullable=False)
    has_bonus = Column(Boolean, default=False, nullable=False)
    bonus_max_points = Column(Float, nullable=True)
    # students can upload files (reports) until the deadline
    has_submission = Column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # students get an e-mail after each upload or delete
    submission_email = Column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at = Column(DateTime, server_default=func.now())


class ExerciseReviews(Base):
    """Review of a user's solution. Each save adds a row; the newest row is valid."""

    __tablename__ = "exercise_reviews"

    itid = Column(Integer, primary_key=True)
    exercise_id = Column(
        Integer, ForeignKey("exercises.itid"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=False, index=True)
    submitted = Column(Boolean, default=False, nullable=False)
    reviewed = Column(Boolean, default=False, nullable=False)
    visible = Column(Boolean, default=True, nullable=False)
    content = Column(Text)
    render_format = Column(String(20), default="MARKDOWN")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())


class ExerciseBonusPoints(Base):
    """Bonus points of a user. Each save adds a row; the newest row is valid."""

    __tablename__ = "exercise_bonus_points"

    itid = Column(Integer, primary_key=True)
    exercise_id = Column(
        Integer, ForeignKey("exercises.itid"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=False, index=True)
    points = Column(Float, default=0, nullable=False)
    visible = Column(Boolean, default=True, nullable=False)
    is_addable = Column(Boolean, default=True, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class ExerciseSubmissions(Base):
    """A file that a user uploaded for an exercise. The row stays after a delete."""

    __tablename__ = "exercise_submissions"

    itid = Column(Integer, primary_key=True)
    exercise_id = Column(
        Integer, ForeignKey("exercises.itid"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=False, index=True)
    # name of the file on the computer of the user
    original_name = Column(String(255), nullable=False)
    # name of the file in the folder of the user and exercise
    stored_name = Column(String(255), nullable=False)
    folder = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    content_type = Column(String(100), nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class SubmissionExtensions(Base):
    """A later deadline for one user and exercise"""

    __tablename__ = "submission_extensions"
    __table_args__ = (UniqueConstraint("exercise_id", "user_id"),)

    itid = Column(Integer, primary_key=True)
    exercise_id = Column(Integer, ForeignKey("exercises.itid"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=False, index=True)
    deadline = Column(DateTime, nullable=False)
    note = Column(String(200))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Downloads(Base):
    """A file that the users can download, e.g. the task of a bonus exercise"""

    __tablename__ = "downloads"

    itid = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    # an exercise with bonus points that the file belongs to
    exercise_id = Column(Integer, ForeignKey("exercises.itid"), index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    visible = Column(Boolean, nullable=False, default=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    content_type = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AdminActions(Base):
    """What an admin changed: who, when, what and for which user"""

    __tablename__ = "admin_actions"

    itid = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    admin_id = Column(Integer)
    action = Column(String(50), nullable=False)
    user_id = Column(Integer, index=True)
    exercise_code = Column(String(20))
    details = Column(Text)


class UIVisibilitySettings(Base):
    __tablename__ = "ui_visibility_settings"

    itid = Column(Integer, primary_key=True)
    ui_key = Column(String(200), nullable=False, unique=True)
    visible = Column(Boolean, default=True, nullable=False)
    description = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ServiceSettings(Base):
    """Per service: does the app create an account for each new user? (admin page "Services creation")"""

    __tablename__ = "service_settings"

    itid = Column(Integer, primary_key=True)
    service = Column(String(50), nullable=False, unique=True)
    create_accounts = Column(Boolean, default=False, nullable=False)
    description = Column(String(200), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BackgroundTask(Base):
    """Long-running job that runs after the response (see app/tasks.py)"""

    __tablename__ = "background_tasks"

    itid = Column(Integer, primary_key=True)
    public_id = Column(String(32), nullable=False, unique=True)
    kind = Column(String(50), nullable=False)
    # user who started the task
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=True, index=True)
    # user that the task is about (e.g. the new user of a registration)
    about_user_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), default="queued", nullable=False, index=True)
    message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    # process that runs the task: if it is gone, the task was lost
    worker_pid = Column(Integer)


class LoginHistory(Base):
    """Each login attempt. Holds the internal user ID, not the e-mail."""

    __tablename__ = "login_history"

    itid = Column(Integer, primary_key=True)
    # empty if the e-mail is not known
    user_id = Column(Integer, nullable=True, index=True)
    # "form" (e-mail and PIN) or "link" (login link of the e-mail)
    method = Column(String(10), nullable=False)
    # "success", "failed" or "blocked" (too many failed logins)
    result = Column(String(10), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class Notification(Base):
    """A message for the users on the page Account (app/notifications.py)"""

    __tablename__ = "notifications"

    itid = Column(Integer, primary_key=True)
    kind = Column(String(20), nullable=False, default="message")
    title = Column(String(200), nullable=False)
    body = Column(Text)    
    user_id = Column(Integer, ForeignKey("users.itid"), index=True)
    audience = Column(String(50))
    event_key = Column(String(100), unique=True)
    created_by = Column(Integer)
    hidden = Column(Boolean, default=False, nullable=False)
    shown_at = Column(DateTime, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now())
    email_test_at = Column(DateTime)
    email_test_to = Column(String(100))
    emailed_at = Column(DateTime)
    emailed_count = Column(Integer, default=0, nullable=False)
    email_subject = Column(String(200))


class NotificationRead(Base):
    """A user has read a notification: it no longer counts on the gear icon"""

    __tablename__ = "notification_reads"
    __table_args__ = (UniqueConstraint("notification_id", "user_id"),)

    itid = Column(Integer, primary_key=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.itid", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=False, index=True)
    read_at = Column(DateTime, server_default=func.now())


class NotificationEmail(Base):
    """The e-mail of a notification to a user: sent, failed, or being sent"""

    __tablename__ = "notification_emails"
    __table_args__ = (UniqueConstraint("notification_id", "user_id"),)

    itid = Column(Integer, primary_key=True)
    notification_id = Column(
        Integer, ForeignKey("notifications.itid", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=False)
    email = Column(String(100))
    # sending, sent, failed
    status = Column(String(10), nullable=False)
    error = Column(String(300))
    updated_at = Column(DateTime, server_default=func.now())


class EmailBatch(Base):
    """One sending of a notification e-mail (a test, or to the users), as sent"""

    __tablename__ = "email_batches"

    itid = Column(Integer, primary_key=True)
    # None: the notification was deleted
    notification_id = Column(Integer, index=True)
    # test, users
    kind = Column(String(10), nullable=False)
    subject = Column(String(300), nullable=False)
    body = Column(Text)
    created_by = Column(Integer)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    finished_at = Column(DateTime)


class EmailBatchItem(Base):
    """One recipient of an EmailBatch: sent or failed"""

    __tablename__ = "email_batch_items"

    itid = Column(Integer, primary_key=True)
    batch_id = Column(
        Integer,
        ForeignKey("email_batches.itid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer)
    email = Column(String(100))
    # sent, failed
    status = Column(String(10), nullable=False)
    error = Column(String(300))
    sent_at = Column(DateTime, server_default=func.now())
