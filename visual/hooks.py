import glob
import os

from flask import g, current_app, redirect, url_for, render_template
from flask_login import current_user

from .core import db
from .util import now


def init_hooks(app):
    @app.before_request
    def update_user_last_active():
        if current_user.is_authenticated:
            if current_user.last_active is None or (now() - current_user.last_active).total_seconds() > 60:
                current_user.last_active = now()
                db.session.commit()

    @app.before_request
    def check_alembic_version():
        if not app.testing and os.path.isfile(os.path.join(app.root_path, 'config.local.py')) and app.env == 'development':
            warning_text = None
            src = os.path.join(app.root_path[: app.root_path.rfind('/')], 'alembic', 'versions')
            listdir_src = sorted(os.listdir(src), reverse=True)
            versions = [v.split('_')[2] for v in listdir_src if v != '__pycache__']
            user_version = db.session.execute('SELECT version_num FROM alembic_version;').first()[0]

            if user_version in versions:
                if user_version != versions[0]:
                    warning_text = "Накати миграцию"
            else:
                warning_text = 'Миграция осталась в другой ветке.'
            if warning_text:
                return render_template('http_errors/503_alembic_error.html', text=warning_text), 503

    @app.after_request
    def deferred_cookies(response):
        for args, kwargs in g.get('deferred_cookies', []):
            try:
                response.set_cookie(*args, **kwargs)
            except TypeError:
                current_app.logger.error('Error setting deferred cookie: {}, {}'.format(args, kwargs))
        return response




