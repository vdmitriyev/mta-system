from flask import render_template, redirect, request, url_for, escape, current_app
from flask_login import login_user, logout_user, login_required, \
    current_user

from . import auth
from .. import db
from .. import models
from .. models import Users
from .. utils.security import make_hash, verify_hash, generate_pin, random_string
#from ..models import User
from sqlalchemy import or_, and_

@auth.route('/login', methods=['GET', 'POST'])
def loginView():
    ''' Handles login'''

    current_app.logger.info('[i] Login process started')
    current_app.logger.info('[i] current_user.is_authenticated: {0}'.format(current_user.is_authenticated))

    if request.method == 'GET':
        uHash = request.values.get('uHash', None)
        if uHash is not None: uHash = escape(uHash)
        pHash = request.values.get('pHash', None)
        if pHash is not None: pHash = escape(pHash)

        if uHash is not None and pHash is not None:
            #print (uHash, pHash)
            if validate_user(uHash, pHash):
                models.create_auth_session(uHash)
            else:
                return render_template('auth/loginError.html')
        else:
            return render_template('auth/login.html')

    if request.method == 'POST':

        input_email = request.values.get('inputEmailField', None)
        if input_email is not None: input_email = escape(input_email)
        input_pin = request.values.get('inputPinField', None)
        if input_pin is not None: input_pin = escape(input_pin)

        if input_email is not None and input_pin is not None:

            u_hash = str(make_hash(input_email, current_app.config['HASH_KEY_LINKS'], AUTH_SIZE=32))
            p_hash = str(make_hash(input_pin, current_app.config['HASH_KEY_LINKS'], AUTH_SIZE=16))

            if validate_user(u_hash, p_hash):
                models.create_auth_session(u_hash)
            else:
                return render_template('auth/loginError.html')
        else:
            return render_template('auth/loginError.html')

    return redirect(url_for('main.viewInfrastructure'))

@auth.route('/logout')
def logout():
    logout_user()
    return render_template('auth/logout.html')

def validate_user(u_hash, p_hash):
    ''' Validate user access '''

    user_exists_rows = db.session.query(Users)\
                                 .filter(and_(Users.url_hash == u_hash, Users.pin_hash == p_hash))\
                                 .all()
    if len(user_exists_rows) > 0:
        return True

    return False

