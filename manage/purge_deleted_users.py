import logging

from flask_babel import gettext, force_locale
from flask import current_app, url_for

from visual.models import User, Tour
from visual.mail import send_email
from visual.core import db

log = logging.getLogger(__name__)


class PurgeDeletedUsers:
    """Удаляет юзеров и все их добро, нажитое непосильным трудом"""

    def run(self, dry=False, nomail=False, loglevel=logging.WARNING):
        log.setLevel(loglevel)
        users = User.query.filter(User.deleted != None).all()

        if dry:
            log.info('DRY MODE: никаких действий в действительности совершено не будет.')

        for user in users:
            with force_locale(user.guess_lang()):
                x_time = user.purge_timedelta().days
                log.debug('User #{user.id} {user.email} (lang={1}): удаление через {0} дней'.format(x_time, user.guess_lang(), user=user))

                # Предупреждения о скором удалении
                if x_time in current_app.config['DELETED_USER_AGONY_WARNINGS']:
                    subj = gettext('Your account will be deleted in %(days)d days', days=x_time)
                    if not dry and not nomail:
                        send_email(
                            subj,
                            [user.email],
                            None,
                            template='mail/delete_user',
                            days=x_time,
                            link=url_for('my.index', path='settings/restore', _external=True, _scheme='https'),
                            user=user
                        )
                    log.info('Отправлено{} письмо "{}" на {}'.format(' (на самом деле нет, потому что --nomail)' if nomail else '', subj, user.email))

                # Удаление юзеров
                if x_time <= 0:
                    for tour in Tour.query.filter_by(user_id=user.id).all():
                        if not dry:
                            tour.delete()
                        log.info('Удалён тур id=%d' % tour.id)

                    if not dry:
                        db.session.delete(user)
                        db.session.commit()
                    log.info('Удалён юзер #{}'.format(user.id))

                    subj = gettext('Your account has been permanently deleted')
                    if not dry and not nomail:
                        send_email(
                            subj,
                            [user.email],
                            None,
                            template='mail/user_destroyed',
                            user=user
                        )
                    log.info('Отправлено{} письмо "{}" на {}'.format(' (на самом деле нет, потому что --nomail)' if nomail else '', subj, user.email))
