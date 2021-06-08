from flask import current_app, redirect, url_for
from flask_login import UserMixin, AnonymousUserMixin
from flask_login import current_user, login_user, login_required, logout_user

from . import db, login_manager

class Users(db.Model):
    ''' Mapping to database table here '''
    __tablename__ = 'users'

    # make object "subscriptable"
    def __getitem__(self, field):
        return self.__dict__[field]

class User(UserMixin):
    ''' Handles user'''
    pass

class AnonymousUser(AnonymousUserMixin):
    ''' Handles anonymous user'''

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
    return redirect(url_for('auth.loginView'))

def create_auth_session(u_hash):
    user = User()
    user.id = u_hash
    login_user(user, remember=True)
