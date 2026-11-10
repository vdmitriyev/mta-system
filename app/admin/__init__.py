from flask import Blueprint

admin = Blueprint("admin", __name__)

from . import views, views_bonus, views_review, views_services
