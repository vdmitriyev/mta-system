import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from flask import render_template, redirect, url_for, abort, flash, request,\
                  current_app, make_response, escape, Markup, jsonify, send_from_directory, send_file

from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from email_validator import validate_email, EmailNotValidError

from . import main
from .. import settings as settings
from .. import db

from ..models import Users
from ..utils.security import make_hash, verify_hash, generate_pin, random_string
from ..utils.captcha import generate_captcha
from ..emailsrv.pyemail import email_content, send_email


from ..utils.pgadmin4_api import new_user_pgadmin4
from ..utils.superset_api import SupersetUser, SupersetAPIClient
from ..utils.metabase_api import create_user_and_docker, UserDataMetabase
from ..utils.openrefine_api import create_user_and_docker_or, UserDataOpenRefine
from ..utils.nifi_api import create_user_and_docker_nifi, UserDataNiFi

# adds constant value to all views
@main.context_processor
def inject_user():
    return dict(courseName = current_app.config["COURSE_NAME_TITLE"])

@main.route('/')
@main.route('/index')
def index():
    return render_template('index.html')

@main.route('/description')
def viewDescription():
    return render_template('description.html')

@main.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        error = None

        inputEmailField = request.values.get('inputEmailField', None)
        if inputEmailField is not None: inputEmailField = escape(inputEmailField)

        inputCodeField = request.values.get('inputCodeField', None)
        if inputCodeField is not None: inputCodeField = escape(inputCodeField)

        inputCaptchaField = request.values.get('inputCaptchaField', None)
        if inputCaptchaField is not None: inputCaptchaField = escape(inputCaptchaField)

        inputCaptchaGUIDField = request.values.get('inputCaptchaGUIDField', None)
        if inputCaptchaGUIDField is not None: inputCaptchaGUIDField = escape(inputCaptchaGUIDField)

        current_app.logger.info('[i] Received the following email for registration: {0}'.format(inputEmailField))

        course_security_code = current_app.config["COURSE_SECURITY_CODE"]

        if inputCodeField is not None: inputCodeField = inputCodeField.upper()
        if course_security_code is not None: course_security_code = course_security_code.upper()

        if (inputEmailField is not None and len(inputEmailField) > 0):
            try:
                validation = validate_email(inputEmailField, check_deliverability=False, allow_smtputf8=False)
                email = validation['email']
            except EmailNotValidError as ex:
                error = '[x] Email is not valid for registration: {0}'.format(ex)
                current_app.logger.info(error)
        else:
            error = 'Provide an email for your registration'

        if error is None:
            if (not (inputCodeField == course_security_code)):
                error = 'Please, provide the correct special code'

        if error is None:
            if (not (verify_hash(inputCaptchaField, inputCaptchaGUIDField, current_app.config["HASH_KEY_HIDDEN"]))):
                error = 'Please, provide the correct captcha'

        if error is None:
            is_registered = False
            try:
                is_registered = register_new_user(inputEmailField)
            except Exception as ex:
                current_app.logger.info('[x] Exception by registration: {0}'.format(ex))

            if (is_registered):
                return render_template('register/registerSuccess.html')
            else:
                return render_template('register/registerAlreadyExists.html')

        return render_template('register/registerTryAgain.html', error = error)

    if request.method == 'GET':
        captcha_txt, captcha_png  = generate_captcha(add_noise=True)
        return render_template('register/register.html', captchaImageAsBase64 = captcha_png,
                                                         inputCaptchaGUIDField = make_hash(captcha_txt, current_app.config["HASH_KEY_HIDDEN"]))


def register_new_user(new_user_email):
    ''' Register a new user in the system '''

    is_registered = False
    new_user_email = new_user_email.strip().lower()
    current_app.logger.info(f'[i] Following e-mail was received for the new registration: {new_user_email}')

    email_exists_rows = db.session.query(Users).filter(Users.email == new_user_email).all()

    # check, if real new user needed
    if len(email_exists_rows) == 0:

        new_pin = generate_pin()
        new_pgadmin4_password = random_string()
        new_postgresql_db, new_postgresql_user, new_postgresql_user_order = new_postgresql_db_names()
        new_postgresql_password = new_pgadmin4_password

        # superset user
        new_superset_login = new_postgresql_user
        new_superset_password = new_pgadmin4_password

        # jupyterhub user
        new_jupyterhub_user = '{0}_{1}'.format(settings.JUPYTERHUB_USER_PREFIX, new_postgresql_user[-2:])
        new_jupyterhub_password = new_pgadmin4_password

        # this is workaround
        pgadmin4_api_via_process(new_user_email, new_pgadmin4_password)

        superset_user(login = new_superset_login,
                      password = new_superset_password,
                      email = new_user_email)

        # metabase user
        new_metabase_password = new_pgadmin4_password
        new_mb_docker_port = int(new_postgresql_user_order) + settings.METABASE_PORT_OFFSET
        current_app.logger.info(f'[i] metabase docker port should be: {new_mb_docker_port}')
        metabase_user(email = new_user_email,
                      password = new_metabase_password,
                      docker_port = new_mb_docker_port)

        # openrefine user
        new_openrefine_user = '{0}_{1}'.format(settings.OPENREFINE_USER_PREFIX, new_postgresql_user[-2:])
        new_openrefine_password = new_pgadmin4_password
        new_openrefine_docker_port = int(new_postgresql_user_order) + settings.OPENREFINE_PORT_OFFSET
        current_app.logger.info(f'[i] openrefine docker port should be: {new_openrefine_docker_port}')
        openrefine_user(user_name = new_openrefine_user,
                        password = new_openrefine_password,
                        docker_port = new_openrefine_docker_port)

        # nifi user
        new_nifi_user = '{0}_{1}'.format(settings.NIFI_USER_PREFIX, new_postgresql_user[-2:])
        new_nifi_password = new_pgadmin4_password
        new_nifi_docker_port = int(new_postgresql_user_order) + settings.NIFI_PORT_OFFSET
        current_app.logger.info(f'[i] nifi docker port should be: {new_nifi_docker_port}')
        nifi_user(user_name = new_nifi_user,
                  password = new_nifi_password,
                  docker_port = new_nifi_docker_port)

        # BUG: DOESN'T WORK IN PRODUCTION, IT IS PURE MAGIC (UNCLEAR WHY EXACTLY)
        # if (new_user_pgadmin4(user_email=new_user_email
        #                       ,user_password=new_pgadmin4_password
        #                       #,logger=logger
        #                       )):
        #     logger.info ('[i] User for pgadmin4 was created or updated')
        # else:
        #     logger.info ('[i] User for pgadmin4 was NOT created or updated')


        if (create_postgresql_db(db_name = new_postgresql_db,
                                 db_user = new_postgresql_user,
                                 db_password = new_postgresql_password)):
            current_app.logger.info ('[i] User and database in PostgreSQL were created.')
        else:
            current_app.logger.info ('[i] User and database in PostgreSQL were NOT created.')

        new_user_hash = str(make_hash(new_user_email, current_app.config["HASH_KEY_LINKS"], AUTH_SIZE=32))
        new_pin_hash = str(make_hash(new_pin, current_app.config["HASH_KEY_LINKS"], AUTH_SIZE=16))

        email_body = email_content(link = '{0}{1}?uHash={2}&pHash={3}'.format(settings.BASE_URL, 'login', new_user_hash, new_pin_hash), pin = new_pin)
        send_email(to_email = new_user_email, subject = 'Registration', content=email_body, settings = current_app.config)

        new_user = Users (
                    email = new_user_email, url_hash = new_user_hash,
                    pin = new_pin, pin_hash = new_pin_hash,
                    pgadmin4_password = new_pgadmin4_password,
                    postgresql_db = new_postgresql_db, postgresql_user = new_postgresql_user, postgresql_password = new_postgresql_password,
                    superset_user = new_superset_login, superset_password = new_superset_password,
                    jupyterhub_user = new_jupyterhub_user, jupyterhub_password = new_jupyterhub_password,
                    metabase_password = new_metabase_password, metabase_docker_port = new_mb_docker_port,
                    openrefine_user = new_openrefine_user, openrefine_password = new_openrefine_password, openrefine_docker_port = new_openrefine_docker_port,
                    nifi_user = new_nifi_user, nifi_password = new_nifi_password, nifi_docker_port = new_nifi_docker_port
        )

        db.session.add(new_user)
        db.session.commit()
        is_registered = True
    else:
        current_app.logger.info ('[i] Following user already exists: {0}'.format(new_user_email))
        resend_email(user_data=email_exists_rows[0])
        is_registered = False

    return is_registered

def resend_email(user_data):
    ''' Resends email if user already registered '''

    email = user_data[0]
    user_hash = user_data[1]
    pin = user_data[2]
    pin_hash = user_data[3]
    email_body = email_content(link = '{0}{1}?uHash={2}&pHash={3}'.format(settings.BASE_URL, 'login', user_hash, pin_hash), pin = pin)
    send_email(to_email = email, subject = 'Registration', content=email_body, settings = current_app.config)

def new_postgresql_db_names():
    ''' Get a new names for database and user '''

    new_db_name, new_db_user = None, None

    # very simple method that simple takes the next int
    # won't work if users/databases will be deleted randomly

    sql_next_cnt = "SELECT count(*)+1 FROM pg_database where datname LIKE '%{dbNamePrefix}%';".format(dbNamePrefix = settings.POSTGRESQL_DB_PREFIX)

    try:
        connection = psycopg2.connect(user = current_app.config["POSTGRESQL_ADMIN_USER"],
                                      password = current_app.config["POSTGRESQL_ADMIN_PASSWORD"],
                                      host = current_app.config["POSTGRESQL_DB_HOST"],
                                      port = current_app.config["POSTGRESQL_DB_HOST_PORT"],
                                      database = current_app.config["POSTGRESQL_DB_NAME"])

        cursor = connection.cursor()
        cursor.execute(sql_next_cnt)
        sql_next_row = cursor.fetchone()

        new_db_user_order = sql_next_row[0]
        new_db_name = '{0}_{1}'.format(settings.POSTGRESQL_DB_PREFIX, str(sql_next_row[0]).zfill(2))
        new_db_user = '{0}_{1}'.format(settings.POSTGRESQL_USER_PREFIX, str(sql_next_row[0]).zfill(2))

    except (Exception, psycopg2.Error) as ex:
        current_app.logger.info ('[e] Error while working with PostgreSQL: {0}'.format(ex))
        is_created = False
    finally:
        if (connection): cursor.close()
        connection.close()
        current_app.logger.info('[i] PostgreSQL connection was closed')

    return new_db_name, new_db_user, new_db_user_order

def pgadmin4_api_via_process(new_user_email, new_pgadmin4_password):
    ''' Using subprocess method to create user in pgadmin4'''

    import subprocess
    current_app.logger.info('[i] Using subprocess method to create user in pgadmin4')

    # full path to script
    #py_script_name = os.path.join(app.root_path, 'utils', 'pgadmin4_api.py')
    py_script_name = os.path.join(current_app.config["BASEDIR"], 'utils', 'pgadmin4_api.py')
    

    # running in another virtualenv
    # if os.name == 'nt':
    #py_interpreter = os.path.join(app.root_path, '..', '.venv', 'Scripts', 'python')
    py_interpreter = os.path.join(current_app.config["BASEDIR"], '..', '.venv', 'Scripts', 'python')
    if os.name == 'posix':
        #py_interpreter = os.path.join(app.root_path, '..', '.venv', 'bin', 'python')
        py_interpreter = os.path.join(current_app.config["BASEDIR"], '..', '.venv', 'bin', 'python')

    #logger.info('[i] py_interpreter: 'py_interpreter)

    # cmd to run
    cmd = '{0} {1} --email {2} --password {3}'.format(py_interpreter, py_script_name,
                                                      new_user_email, new_pgadmin4_password)
    p = subprocess.Popen(cmd, shell = True)

def superset_user(login, password, email):
    ''' Creates superset user'''

    obj = SupersetAPIClient(SupersetUser(login=login, password=password, email=email))
    obj.create_new_user()

def metabase_user(email, password, docker_port):
    ''' Creates metabase user and docker container'''

    tokens = email_to_name(email)

    mb_user = UserDataMetabase(fname = tokens[0].title(),
                               lname = tokens[1].title(),
                               email = email,
                               password = password)

    if create_user_and_docker(user_data = mb_user, docker_port = docker_port):
        current_app.logger.info(f'[i] metabase docker and user were created successfully. Email: {email}')
    else:
        current_app.logger.info(f'[e] metabase docker and user were NOT created successfully. Email: {email}')

def openrefine_user(user_name, password, docker_port):
    ''' Creates openrefine user and docker container'''

    or_user = UserDataOpenRefine(userName = user_name, password = password)

    if create_user_and_docker_or(user_data = or_user, docker_port = docker_port):
        current_app.logger.info(f'[i] openrefine docker and user were created successfully. User: {user_name}')
    else:
        current_app.logger.info(f'[e] openrefine docker and user were NOT created successfully. User: {user_name}')

def nifi_user(user_name, password, docker_port):
    ''' Creates nifi user and docker container'''

    nifi_user = UserDataNiFi(userName = user_name, password = password)

    if create_user_and_docker_nifi(user_data = nifi_user, docker_port = docker_port):
        current_app.info(f'[i] NiFi docker and user were created successfully. User: {user_name}')
    else:
        current_app.info(f'[e] NiFi docker and user were NOT created successfully. User: {user_name}')

def create_postgresql_db(db_name, db_user, db_password, verbose=True):
    ''' Create new database and user in the PostgreSQL database '''

    is_created = False

    sql_crt_role_01 = '''CREATE ROLE {0} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOLOGIN;'''.format(db_name)
    sql_crt_role_02 = '''CREATE ROLE {0} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN ENCRYPTED PASSWORD '{1}';'''.format(db_user, db_password)

    sql_grant_01 = '''GRANT {0} TO {1};'''.format(db_name, db_user)
    sql_grant_demo_01 = '''GRANT CONNECT ON DATABASE {db_demo} TO {db_user}'''.format(db_demo = current_app.config["POSTGRESQL_DEMO_DB"], db_user=db_user)
    sql_crt_db = '''CREATE DATABASE {0} WITH OWNER={1};'''.format(db_name, db_user)
    sql_revoke = '''REVOKE ALL ON DATABASE {0} FROM public;'''.format(db_name)

    try:
        connection = psycopg2.connect(user = current_app.config["POSTGRESQL_ADMIN_USER"],
                                      password = current_app.config["POSTGRESQL_ADMIN_PASSWORD"],
                                      host = current_app.config["POSTGRESQL_DB_HOST"],
                                      port = current_app.config["POSTGRESQL_DB_HOST_PORT"],
                                      database = current_app.config["POSTGRESQL_DB_NAME"])

        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = connection.cursor()

        # PostgreSQL Connection properties
        if verbose: print ('[i] PostgreSQL DNS parameters: {0}'.format(connection.get_dsn_parameters(),"\n"))

        # PostgreSQL version
        # if verbose:
        #     cursor.execute("SELECT version();")
        #     record = cursor.fetchone()
        #     print('[i] You are connected to the following PostgreSQL database: {0}'.format(record[0]))

        cursor.execute(sql_crt_role_01)
        cursor.execute(sql_crt_role_02)
        cursor.execute(sql_grant_01)
        cursor.execute(sql_crt_db)
        cursor.execute(sql_revoke)
        cursor.execute(sql_grant_demo_01)
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.info ('[e] Error while working with PostgreSQL: {0}'.format(ex))
        is_created = False
    finally:
        if (connection): cursor.close()
        connection.close()
        current_app.logger.info('[i] PostgreSQL connection was closed')

    # open connection to newly created database to provide it with some grants
    sql_newdb_grant = '''GRANT ALL ON SCHEMA public TO {0} WITH GRANT OPTION;'''.format(db_user)
    try:
        current_app.logger.info ('[i] Connecting to the new database')
        connection_new_db = psycopg2.connect(user = db_user,
                                             password = db_password,
                                             host = current_app.config["POSTGRESQL_DB_HOST"],
                                             port = current_app.config["POSTGRESQL_DB_HOST_PORT"],
                                             database = db_name)
        connection_new_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor_new_db = connection_new_db.cursor()
        cursor_new_db.execute(sql_newdb_grant)
        is_created = True
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.info ('[e] Error while working with PostgreSQL: {0}'.format(ex))
        is_created = False
    finally:
        if (connection_new_db):
            cursor_new_db.close()
        connection_new_db.close()

    #
    # open connection to demo database to provide it with some grants
    # this can be done only under demo user profile
    #
    sql_demodb_grant = '''GRANT SELECT ON ALL TABLES IN SCHEMA public TO {db_user};'''.format(db_user=db_user)
    sql_demodb_grant_alt ='''ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {db_user};'''.format(db_user=db_user)
    connection_demo_db = None
    try:
        current_app.logger.info ('[i] Connecting to the demo database')
        connection_demo_db = psycopg2.connect(user = current_app.config["POSTGRESQL_DEMO_USER"],
                                              password =  current_app.config["POSTGRESQL_DEMO_PASSWORD"],
                                              host = current_app.config["POSTGRESQL_DB_HOST"],
                                              port = current_app.config["POSTGRESQL_DB_HOST_PORT"],
                                              database = current_app.config["POSTGRESQL_DEMO_DB"])
        connection_demo_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor_demo_db = connection_demo_db.cursor()
        cursor_demo_db.execute(sql_demodb_grant)
        cursor_demo_db.execute(sql_demodb_grant_alt)
        is_created = True
    except (Exception, psycopg2.Error) as ex:
        current_app.logger.info ('[e] Error while working with PostgreSQL: {0}'.format(ex))
        is_created = False
    finally:
        if (connection_demo_db):
            cursor_demo_db.close()
        cursor_demo_db.close()

    return is_created

def hlp_init_postgresql_demo():
    ''' Initiate PostgreSQL demo database - required for a teaching course.
        This function should be run, if needee.
        For a moment, it won't be executed automatically by the system. 
    '''

    # create demo user and databsae for the 
    if (create_postgresql_db(db_name = current_app.config["POSTGRESQL_DEMO_DB"],
                             db_user = current_app.config["POSTGRESQL_DEMO_USER"],
                             db_password = current_app.config["POSTGRESQL_DEMO_PASSWORD"])):
        print ('[i] User and database in PostgreSQL were created.')
    else:
        print ('[i] User and database in PostgreSQL were NOT created.')


def email_to_name(email):
    ''' Fetches name from the email: <name>.<surmane>@domain. '''
    tokens = email[:email.find('@')].split('.')
    for _ in range(len(tokens), 2):
        tokens.append('Unknown')
    return tokens

@main.route('/infrastructure', methods=['GET'])
@login_required
def viewInfrastructure():
    ''' Handles view with infrastructure'''

    #current_app.logger.info('[i] current_user.get_id(): {0}'.format(current_user.get_id()))

    info_message = request.values.get('message')
    if info_message is not None: info_message = escape(info_message)
    cmd = request.values.get('cmd')
    if cmd is not None: cmd = escape(cmd)

    cmd_start_mb = 'startMetabase'
    cmd_start_or = 'startOpenrefine'
    cmd_start_nifi = 'startNiFi'

    user_data = get_user_data(current_user.get_id())

    if user_data:

        # start container if command supplied
        if cmd is not None:
            if cmd.upper() == cmd_start_mb.upper():
                info_message = start_docker_container(user_data, service_type='metabase')
            if cmd.upper() == cmd_start_or.upper():
                info_message = start_docker_container(user_data, service_type='openrefine')
            if cmd.upper() == cmd_start_nifi.upper():
                info_message = start_docker_container(user_data, service_type='nifi')
            return redirect(f'infrastructure?message={info_message}')

        superset_sqlalchermy_uri = construct_db_uri_for_user(user_data)

        metabase_url_tpl = 'https://{backend}/metabase/{dockerPort}/'
        metabase_url = metabase_url_tpl.format(backend = settings.BASE_BACKEND,
                                               dockerPort = user_data['metabase_docker_port'])

        openrefine_url_tpl = 'https://{backend}/openrefine/{dockerPort}/'
        openrefine_url = openrefine_url_tpl.format(backend = settings.BASE_BACKEND,
                                                   dockerPort = user_data['openrefine_docker_port'])

        nifi_url_tpl = 'https://{backend}/nifi/{dockerPort}/nifi/'
        nifi_url = nifi_url_tpl.format(backend = settings.BASE_BACKEND,
                                       dockerPort = user_data['nifi_docker_port'])
        nifi_db_connection_url = f"jdbc:postgresql://{settings.BASE_BACKEND}:5432/{user_data['postgresql_db']}"

        mb_container_status, or_container_status, nifi_container_status = user_containers_status(user_data)

        return render_template('infrastructure.html',
                                                      # pgAdmin4
                                                      pgadmin4URL = settings.PGADMIN4_URL,
                                                      pgadmin4Login = user_data['email'],
                                                      pgadmin4Password = user_data['pgadmin4_password'],
                                                      # postgresql
                                                      postgresqlServer = settings.POSTGRESQL_SERVER,
                                                      postgresqlServerPort = settings.POSTGRESQL_SERVER_PORT,
                                                      postgresqlDB = user_data['postgresql_db'],
                                                      postgresqlUser = user_data['postgresql_user'],
                                                      postgresqlPassword = user_data['postgresql_password'],
                                                      # superset
                                                      supersetURL = settings.SUPERSET_URL,
                                                      supersetUser = user_data['superset_user'],
                                                      supersetPassword = user_data['superset_password'],
                                                      supersetSQLAlchemyURI= superset_sqlalchermy_uri,
                                                      # JupyterHub
                                                      jupyterhubURL = settings.JUPYTERHUB_URL,
                                                      jupyterhubUser = user_data['jupyterhub_user'],
                                                      jupyterhubPassword = user_data['jupyterhub_password'],
                                                      # Metabase
                                                      metabaseEmail = user_data['email'],
                                                      metabasePassword = user_data['metabase_password'],
                                                      metabaseURL = metabase_url,
                                                      metabaseStartCmd = cmd_start_mb,
                                                      metabaseContainerStatus = Markup(mb_container_status),
                                                      # OpenRefine
                                                      openrefineUser = user_data['openrefine_user'],
                                                      openrefinePassword = user_data['openrefine_password'],
                                                      openrefineURL = openrefine_url,
                                                      openrefineStartCmd = cmd_start_or,
                                                      openrefineContainerStatus = Markup(or_container_status),
                                                      # NiFi
                                                      nifiUser = user_data['nifi_user'],
                                                      nifiPassword = user_data['nifi_password'],
                                                      nifiURL = nifi_url,
                                                      nifiStartCmd = cmd_start_nifi,
                                                      nifiContainerStatus = Markup(nifi_container_status),
                                                      nifiDBConnectionURL = nifi_db_connection_url,
                                                      serviceVisibility = settings.service_visibility,
                                                      message = info_message
                                                      )
    else:
        return render_template('infrastructure.html', message = info_message)

def construct_db_uri_for_user(user_data):
    ''' Constructs DB URI for particular user '''

    uri_tpl = 'postgresql://{db_user}:{db_password}@{db_backend}/{db_name}'
    superset_sqlalchermy_uri = uri_tpl.format(db_user = user_data['postgresql_user'],
                                              db_password = user_data['postgresql_password'],
                                              db_name = user_data['postgresql_db'],
                                              db_backend = current_app.config['POSTGRESQL_DB_HOST'])
    return superset_sqlalchermy_uri

def start_docker_container(user_data, service_type):
    ''' Starts docker container'''

    message = None
    try:
        import docker
        client = docker.from_env()
        docker_port = user_data[f'{service_type}_docker_port']
        container_name = f'{service_type}-{docker_port}'
        current_app.logger.info(f'[i] Start container: {container_name}')
        docker_container = client.containers.get(container_name)
        if docker_container is not None:
            docker_container.start()
            message = '[i] Service should be running. Be patient, the process may take a while'
        else:
            message = '[x] This service was not found'
    except Exception as ex:
        print(f'[e] Exception {ex}')
        message = f'[e] Exception happened'

    return message

def user_containers_status(user_data):
    ''' Gets docker container status of user'''

    mb_container_status = '''<span class="badge badge-secondary">Unknown</span>'''
    or_container_status = '''<span class="badge badge-secondary">Unknown</span>'''
    nifi_container_status = '''<span class="badge badge-secondary">Unknown</span>'''

    try:
        import docker
        client = docker.from_env()

        # metabase
        mb_container = client.containers.get(f'metabase-{user_data["metabase_docker_port"]}')
        if mb_container is not None:
            mb_container_status = container_status_to_html(mb_container.status)

        # openrefine
        or_container = client.containers.get(f'openrefine-{user_data["openrefine_docker_port"]}')
        if or_container is not None:
            or_container_status = container_status_to_html(or_container.status)

        # nifi
        nifi_container = client.containers.get(f'nifi-{user_data["nifi_docker_port"]}')
        if nifi_container is not None:
            nifi_container_status = container_status_to_html(nifi_container.status)

    except ImportError as ex:
        print(f'[e] No module installed: docker. Exception {ex}')
        return mb_container_status, or_container_status, nifi_container_status
    except OSError as ex:
        print(f'[e] No access to docker. Exception {ex}')
        return mb_container_status, or_container_status, nifi_container_status
    except Exception as ex:
        print(f'[e] Exception {ex}')
        return mb_container_status, or_container_status, nifi_container_status

    return mb_container_status, or_container_status, nifi_container_status

def container_status_to_html(current_status):
    ''' Presents given status as HTML '''

    container_status = '''<span class="badge badge-secondary">Unknown</span>'''
    if str(current_status) == 'running':
        container_status = '''<span class="badge badge-success">running</span>'''
    if str(current_status) == 'exited':
        container_status = '''<span class="badge badge-danger">exited</span>'''

    return container_status

def get_user_data(u_hash):
    ''' Gets user data from database'''

    user_data_rows = db.session.query(Users)\
                               .filter(and_(Users.url_hash == u_hash, Users.deleted == False))\
                               .order_by(Users.created_at.desc())\
                               .limit(1)\
                               .all()
    user_data = {}

    # useless because of the limit, but let's keep for a while
    if len(user_data_rows) > 1:
        current_app.logger.info(f'[e] More users that expected were found for bash: {u_hash}')
        return user_data

    if len(user_data_rows) > 0:
        user = user_data_rows[0]
        col_ignore = ['itid', 'deleted', 'created_at']
        for col in user.__table__.columns:
            if col.name not in col_ignore:
                user_data[col.name] = user[col.name]
    else:
        current_app.logger.info(f'[e] No such user was found: {u_hash}')
    return user_data


@main.route('/importer', methods=['GET'])
@login_required
def viewImporter():
    ''' Handles importer actions'''

    dataset = escape(request.values.get('dataset', None))
    datasets_available = ['flights', 'airbnb', 'adventureworks']
    current_app.logger.info(f'[i] Dataset for importer: {dataset}')
    info_message = f'Adding dataset: {dataset}'

    if dataset is not None:
        if dataset not in datasets_available:
            return redirect(url_for('main.viewInfrastructure', message = '[x] No such dataset'))

        user_data = get_user_data(current_user.get_id())

        if user_data is None:
            return redirect(url_for('main.viewInfrastructure'))

        postgresql_db_uri = construct_db_uri_for_user(user_data)

        # flights
        if dataset == datasets_available[0]:
            current_app.logger.info(f'[i] Importing {dataset} for user {current_user.get_id()}')
            from ..importers.flights import importer_flights as flights
            try:
                flights.run_import(db_connect_uri  = postgresql_db_uri)
            except Exception as ex:
                current_app.logger.error(ex, exc_info=True)
                info_message = f'[x] Error: {str(ex)}'
            current_app.logger.info(f'[i] Imported {dataset} for user {current_user.get_id()}')

        # airbnb
        if dataset == datasets_available[1]:
            current_app.logger.info(f'[i] Importing {dataset} for user {current_user.get_id()}')
            from ..importers.airbnb import importer_airbnb_csv as airbnb
            try:
                airbnb.run_import(db_connect_uri = postgresql_db_uri)
            except Exception as ex:
                current_app.logger.error(ex, exc_info=True)
                info_message = f'[x] Error: {str(ex)}'
            current_app.logger.info(f'[i] Imported {dataset} for user {current_user.get_id()}')

        # adventureworks
        if dataset == datasets_available[2]:
            current_app.logger.info(f'[i] Importing {dataset} for user {current_user.get_id()}')
            from ..importers.adventureworks_custom import importer_adventureworks_custom as adventureworks
            try:
                adventureworks.run_import(postgresql_db_uri)
            except Exception as ex:
                current_app.logger.error(ex, exc_info=True)
                info_message = f'[x] Error: {str(ex)}'
            current_app.logger.info(f'[i] Imported {dataset} for user {current_user.get_id()}')

    return redirect(url_for('main.viewInfrastructure', message = info_message))
