from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

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


# Name of a service (as in SERVICES_UI) -> table with the accounts of the users
SERVICE_MODELS = {
    "postgresql": PostgreSQLService,
    "pgadmin4": PGAdmin4Service,
    "metabase": MetabaseService,
    "openrefine": OpenRefineService,
    "jupyterhub": JupyterHubService,
    "nifi": NiFiService,
    "superset": SupersetService,
    "mariadb": MariaDBService,
    "wordpress": WordpressService,
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


class UIVisibilitySettings(Base):
    __tablename__ = "ui_visibility_settings"

    itid = Column(Integer, primary_key=True)
    ui_key = Column(String(200), nullable=False, unique=True)
    visible = Column(Boolean, default=True, nullable=False)
    description = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ServiceSettings(Base):
    """Per service: does the app create an account for each new user? (admin page "Auto creation")"""

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
    user_id = Column(Integer, ForeignKey("users.itid"), nullable=True, index=True)
    status = Column(String(20), default="queued", nullable=False, index=True)
    message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    # process that runs the task: if it is gone, the task was lost
    worker_pid = Column(Integer)
