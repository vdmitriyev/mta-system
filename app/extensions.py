import redis
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from rq import Queue

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

# r_connect, rq_worker = None, None
r_connect = redis.Redis(host="redis", port=6379, password="redisqydGIZQvyER")
rq_worker = Queue(connection=r_connect)


def register_extensions(app):
    """Register flask extensions to be used by the app

    Args:
        app (flask): initialized flask app
    """

    db.init_app(app)
    login_manager.init_app(app)
    # SQLite can change tables only in "batch" mode
    migrate.init_app(app, db, render_as_batch=True)
