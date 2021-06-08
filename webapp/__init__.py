from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()

def create_app(config):

    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    db.reflect(app=app)

    login_manager.init_app(app)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='')

    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/mtas-admin')

    from .errors import errors as errors_blueprint
    app.register_blueprint(errors_blueprint)

    return app
