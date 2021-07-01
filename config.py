import os
import json
from dotenv import load_dotenv

def load_envs():
    ''' Loads environmental variables from the file'''

    basedir = os.path.abspath(os.path.dirname(__file__))

    if os.environ.get('ENV_FILE') is not None:
        env_file = os.environ.get('ENV_FILE')
        if not os.path.exists(env_file):
            print (f'Give file with environmental variables does not exist: {env_file}')
            load_dotenv(os.path.join(basedir, '.env'))
        else:
            load_dotenv(os.path.join(env_file))
    else:
        load_dotenv(os.path.join(basedir, '.env'))

load_envs()

def get_connection_string():

    DB_CONNECT_URI = 'postgresql://{db_user}:{db_password}@{db_backend}:{db_port}/{db_name}'
    db_port = os.environ.get('MTASBACKEND_DB_HOST_PORT') or 5432
    db_connect = DB_CONNECT_URI.format(db_user = os.environ.get('MTASBACKEND_DB_USER'),
                                       db_password = os.environ.get('MTASBACKEND_DB_USER_PASSWORD'),
                                       db_name = os.environ.get('MTASBACKEND_DB_NAME'),
                                       db_port = db_port,
                                       db_backend = os.environ.get('MTASBACKEND_DB_HOST'))
    return db_connect

class BaseAppConfigs:
    '''Defines base configuration for the flask app '''
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    print(f'Projects base dir: {BASEDIR}')

    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
    HASH_KEY_HIDDEN = str.encode(os.environ.get('HASH_KEY_HIDDEN'))
    HASH_KEY_LINKS = str.encode(os.environ.get('HASH_KEY_LINKS'))
    COURSE_SECURITY_CODE = os.environ.get('COURSE_SECURITY_CODE') or 'CODE'
    COURSE_NAME_TITLE = os.environ.get('COURSE_NAME_TITLE') or None
    
    # SERVER_BIND_HOST = os.environ.get('SERVER_BIND_HOST') or '127.0.0.1'
    # SERVER_BIND_PORT = os.environ.get('SERVER_BIND_PORT') or 5151

    if os.environ.get('SYSTEM_ADMINS') is not None:
        SYSTEM_ADMINS = os.environ.get('SYSTEM_ADMINS').split(';')
    else:
        SYSTEM_ADMINS = []

    # e-mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'localhost'
    MAIL_PORT = os.environ.get('MAIL_PORT') or 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or None
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or None
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or None
    MAIL_ADMIN_NOTIFICATIONS = os.environ.get('MAIL_ADMIN_NOTIFICATIONS') or None

    #
    # mta-system settings
    #
    
    # PostgreSQL to store data 
    POSTGRESQL_DB_HOST = os.environ.get('POSTGRESQL_DB_HOST') or 'localhost'
    POSTGRESQL_DB_HOST_PORT = os.environ.get('POSTGRESQL_DB_HOST_PORT') or '5432'
    POSTGRESQL_DB_NAME = os.environ.get('POSTGRESQL_DB_NAME') or 'postgres'
    POSTGRESQL_ADMIN_USER = os.environ.get('POSTGRESQL_ADMIN_USER') or 'postgres'
    POSTGRESQL_ADMIN_PASSWORD = os.environ.get('POSTGRESQL_ADMIN_PASSWORD') or 'postgres'

    POSTGRESQL_DEMO_DB = os.environ.get('POSTGRESQL_DEMO_DB') or 'db_demo'
    POSTGRESQL_DEMO_USER = os.environ.get('POSTGRESQL_DEMO_USER') or 'db_user_demo'
    POSTGRESQL_DEMO_PASSWORD = os.environ.get('POSTGRESQL_DEMO_PASSWORD') or 'postgres'

    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(BaseAppConfigs):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = get_connection_string()

class ProductionConfig(BaseAppConfigs):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_connection_string()

config_dict = {
    'development'   : DevelopmentConfig,
    'production'    : ProductionConfig,
    'default'       : DevelopmentConfig
}

