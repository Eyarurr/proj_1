import logging

from datetime import datetime, timedelta
from flask import current_app

from visual.models import User, Tour
from visual.core import db

log = logging.getLogger('clean_unconfirmed_users')


class CleanUnconfirmedUsers:
    """Удаляет юзеров, не подтвердивших e-mail, через config['CLEAN_UNCONFIRMED_USERS_LIFETIME']"""
    def run(self, loglevel=None, dry=None):
        log.setLevel(loglevel)

        users = User.query\
            .outerjoin(Tour, Tour.user_id == User.id)\
            .filter(User.last_active == None) \
            .filter(User.created_by == None) \
            .filter(User.email_confirmed == False) \
            .filter(Tour.id == None) \
            .filter(datetime.now() - User.created > timedelta(hours=current_app.config['CLEAN_UNCONFIRMED_USERS_LIFETIME'])) \
            .all()

        for user in users:
            if not dry:
                db.session.delete(user)
            log.info('Юзер #{u.id} {u.email} "{u.name}" НИЗВЕРГНУТ В НЕБЫТИЕ.'.format(u=user))

        if not dry:
            db.session.commit()
