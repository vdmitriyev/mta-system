from app.extensions import db


def configure_database(app):
    pass


# def configure_database(app):

#     #@app.before_first_request
#     def initialize_database():
#         db.create_all()
#         #from app.cli import _import_exercises
#         #_import_exercises()

#     @app.teardown_request
#     def shutdown_session(exception=None):
#         db.session.remove()
