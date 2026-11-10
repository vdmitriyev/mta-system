from flask import Flask
from werkzeug.middleware.profiler import ProfilerMiddleware

from app.cli import register_commands
from app.database import configure_database
from app.extensions import register_extensions


def create_app(config):
    """Creates flask app

    Args:
        config (_type_): Configuration of the flask

    Returns:
        _type_: flask application object
    """

    app = Flask(__name__)
    app.config.from_object(config)
    register_blueprints(app)
    register_extensions(app)
    # configure_database(app)

    from app.main.shared_helpers import add_default_ui_visibility_settings

    with app.app_context():
        add_default_ui_visibility_settings()

    register_commands(app)

    # app.wsgi_app = ProfilerMiddleware(app.wsgi_app, profile_dir='.profile')

    return app


def register_blueprints(app):
    """Imports and registers all blueprints"""

    from .main import main as main_blueprint

    app.register_blueprint(main_blueprint)

    from .auth import auth as auth_blueprint

    app.register_blueprint(auth_blueprint, url_prefix="")

    from .admin import admin as admin_blueprint

    app.register_blueprint(admin_blueprint, url_prefix="/mtas-admin")

    from .errors import errors as errors_blueprint

    app.register_blueprint(errors_blueprint)
