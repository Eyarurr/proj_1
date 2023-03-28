from flask import Blueprint

mod = Blueprint('tutorials', __name__, url_prefix='/tutorials')

from . import views
