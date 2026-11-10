from flask import redirect, url_for
from flask_login import AnonymousUserMixin, UserMixin, login_user
from sqlalchemy import (  # UniqueConstraint,
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

from app.extensions import db, login_manager


class Users(db.Model):
    """Mapping to database table here"""

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

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class PostgreSQLService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "postgresql_service"

    itid = Column(Integer, primary_key=True)
    # user_id                = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.itid"))
    postgresql_db = Column(String(50), nullable=False)
    postgresql_user = Column(String(50), nullable=False)
    postgresql_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class PGAdmin4Service(db.Model):
    """Mapping to database table here"""

    __tablename__ = "pgadmin4_service"

    itid = Column(Integer, primary_key=True)
    # user_id                 = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.itid"))
    pgadmin4_user = Column(String(50), nullable=False)
    pgadmin4_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class MetabaseService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "metabase_service"

    itid = Column(Integer, primary_key=True)
    # user_id                 = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.itid"))
    metabase_login = Column(String(50), nullable=False)
    metabase_password = Column(String(50), nullable=False)
    metabase_docker_port = Column(Integer, nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class OpenRefineService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "openrefine_service"

    itid = Column(Integer, primary_key=True)
    # user_id                 = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.itid"))
    openrefine_user = Column(String(50))
    openrefine_password = Column(String(50))
    openrefine_docker_port = Column(Integer)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class JupyterHubService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "jupyterhub_service"

    itid = Column(Integer, primary_key=True)
    # user_id                 = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.itid"))
    jupyterhub_user = Column(String(50))
    jupyterhub_password = Column(String(50))
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class NiFiService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "nifi_service"

    itid = Column(Integer, primary_key=True)
    # user_id                 = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.itid"))
    nifi_user = Column(String(50))
    nifi_password = Column(String(50))
    nifi_docker_port = Column(Integer)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class SupersetService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "superset_service"

    itid = Column(Integer, primary_key=True)
    # user_id                 = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.itid"))
    superset_user = Column(String(50), nullable=False)
    superset_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class MariaDBService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "mariadb_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    mariadb_db = Column(String(50), nullable=False)
    mariadb_user = Column(String(50), nullable=False)
    mariadb_password = Column(String(50), nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class WordpressService(db.Model):
    """Mapping to database table here"""

    __tablename__ = "wordpress_service"

    itid = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.itid"))
    wordpress_login = Column(String(50), nullable=False)
    wordpress_password = Column(String(50), nullable=False)
    wordpress_docker_port = Column(Integer, nullable=False)
    created = Column(Boolean, default=False, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class Exercises(db.Model):
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
    # parts of the exercise
    has_review = Column(Boolean, default=True, nullable=False)
    has_bonus = Column(Boolean, default=False, nullable=False)
    bonus_max_points = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class ExerciseReviews(db.Model):
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

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class ExerciseBonusPoints(db.Model):
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

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class UIVisibilitySettings(db.Model):
    """Mapping to database table here"""

    __tablename__ = "ui_visibility_settings"

    itid = Column(Integer, primary_key=True)
    ui_key = Column(String(200), nullable=False, unique=True)
    visible = Column(Boolean, default=True, nullable=False)
    description = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __getitem__(self, field):
        '''Makes object "subscriptable"'''
        return self.__dict__[field]


class User(UserMixin):
    """Handles user"""

    pass


class AnonymousUser(AnonymousUserMixin):
    """Handles anonymous user"""

    def can(self, permissions):
        return False

    def is_administrator(self):
        return False

    def check_role(self, role):
        return False


login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(uHash):
    # user = Users.query.get(int(user_id))
    # user.is_admin = user.check_admin()
    # return user

    user = User()
    user.id = uHash
    return user


@login_manager.unauthorized_handler
def unauth_handler():
    return redirect(url_for("auth.loginView"))


def create_auth_session(u_hash):
    user = User()
    user.id = u_hash
    login_user(user, remember=True)
