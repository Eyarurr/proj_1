from flask import Blueprint, render_template, request, url_for, redirect
from flask_login import current_user

mod = Blueprint('my', __name__, url_prefix='/my')


@mod.before_request
def check_access():
    # Список эндпоинтов, где проверка авторизации не нужна
    exempt = ('my.settings_payment_complete', )
    if request.url_rule.endpoint not in exempt and not current_user.is_authenticated:
        return render_template('my/login.html')

    if not request.path.startswith('/my/settings/restore') and current_user.is_authenticated and current_user.deleted:
        return redirect(url_for('my.index', path='settings/restore/'))


from . import views
