from flask import Blueprint

mod = Blueprint('support', __name__, url_prefix='/support')

from . import views
