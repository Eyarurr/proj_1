from functools import wraps

from flask import render_template, request, redirect, url_for, flash, Blueprint, g
from flask_login import login_user, current_user

from ..models import User, NewsArticle, TeamMember
from visual.core import db

mod = Blueprint('admin', __name__, url_prefix='/admin')


def roles_required(*roles):
    def real_decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.has_role(*roles):
                return render_template('admin/access_denied.html', roles=roles, ROLES=TeamMember.ROLES), 403
            return f(*args, **kwargs)
        return wrapper
    return real_decorator


from . import team
from . import users
from . import tours
from . import news
from . import feeds
from . import sources
from . import partners
from . import vacancies
from . import footages
from . import statistics
from . import links
from . import gallery
from . import support
from . import sys
from . import keys
from . import multitours
from . import files_manager
from . import hardware
from . import bladerunner
from . import estates


@mod.before_request
def check_access():
    if request.endpoint == 'admin.index':
        return

    if not current_user.is_authenticated or current_user.banned or current_user.deleted or not current_user.team_member:
        flash('Вы не являетесь членом команды и в админку вам нельзя.', 'danger')
        return redirect(url_for('front.index'))

    if not current_user.has_role('admin.access'):
        flash('У вас нет доступа в админку.', 'danger')
        return redirect(url_for('front.index'))


@mod.before_request
def count_unread_news():
    if current_user.is_authenticated:
        q = db.session.query(db.func.count(NewsArticle.id))
        if current_user.settings_obj.news_last_seen:
            q = q.filter(NewsArticle.created > current_user.settings_obj.news_last_seen)
        g.cnt_new_news = q.scalar()


@mod.before_request
def set_lang():
    g.lang = 'ru'


@mod.route('/', methods=('GET', 'POST'))
def index():
    if current_user.is_authenticated:
        return redirect(url_for('.users'))

    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()

        if user and User.hash_password(request.form.get('password', '')) == user.password_hash:
            if login_user(user, remember=True):
                return redirect(url_for('admin.team'))
            else:
                flash('Вы заблокированы.', 'danger')
        else:
            flash('Неправильно.', 'danger')

    return render_template('admin/index.html')


@mod.route('/server-debug/')
def server_debug():
    return '<pre>' + str(request.headers) + '\n\n' + str(request.environ) + '\n\n' + request.remote_addr + '</pre>'
