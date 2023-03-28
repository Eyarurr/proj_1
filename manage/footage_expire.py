import logging

from datetime import datetime

from flask import current_app
from flask_babel import gettext, force_locale

from visual.models import Footage, User
from visual.mail import send_email
from visual.core import db

log = logging.getLogger(__name__)


class FootageExpire:
    """Удаляет туры, которые попадают в условия из TOUR_LIFETIME"""
    def run(self, quiet=False, dry=False, loglevel=logging.WARNING):
        log.setLevel(loglevel)

        if dry:
            log.info('DRY MODE: никаких действий в действительности совершено не будет.')

        tour_lifetime = current_app.config.get('TOUR_LIFETIME')
        # {
        #    user_id: {
        #        'email': user.email,
        #        'delete': [tour.title, ...],
        #        'notify': [(tour.title, days_left, tour.user_id, tour.id), ...],
        #    }
        # }
        notifications = {}

        for status, conf in tour_lifetime.items():
            footages = Footage.query\
                .filter(Footage.status == status, Footage.type.in_(['virtual', 'real']))\
                .order_by(Footage.id.desc())\
                .all()

            for footage in footages:
                tours_updated = [(datetime.now(tz=tour.updated.tzinfo) - tour.updated).days for tour in footage.tours]
                tour_min_age = min(tours_updated) if tours_updated else None

                age = min(footage.age(), tour_min_age) if tour_min_age else footage.age()

                # Удаление
                if age > conf['lifetime']:
                    if age == tour_min_age and tour_min_age != footage.age():
                        note = '(оценка по времени жизни тура)'
                    else:
                        note = ''
                    log.info('DELETE footage {0.status}, #{0.id} живёт {1} дн (лимит {2} дн). {3}'.format(footage, age, conf['lifetime'], note))

                    for tour in footage.tours:
                        user = tour.user

                        log.info('    DELETE tour #{}'.format(tour.id))
                        if not dry:
                            tour.delete()
                        if user.email_notifications:
                            if user.id not in notifications:
                                notifications[user.id] = {'delete': [], 'notify': [], 'email': user.email}
                            notifications[user.id]['delete'].append(tour.title)

                    if not dry:
                        footage.delete()
                        db.session.commit()

                # Предупреждения
                elif age - conf['lifetime'] in conf['warn']:
                    log.info('NOTIFY footage {0.status}, id {0.id} живёт {1} дн, осталось {2} дн.'.format(footage, age, conf['lifetime'] - age))

                    for tour in footage.tours:
                        user = tour.user
                        log.info('    NOTIFY tour #{0.id} to {1.email}'.format(tour, user))

                        if user.email_notifications:
                            if user.id not in notifications:
                                notifications[user.id] = {'delete': [], 'notify': [], 'email': user.email}
                            notifications[user.id]['notify'].append((tour.title, conf['lifetime']-age, tour.user.id, tour.id))

        for user_id in notifications.keys():
            user = User.query.get(user_id)
            with force_locale(user.guess_lang()):
                subj = gettext('Notification about your tours expiration/deletion')
                if not dry:
                    send_email(
                        subj,
                        [notifications[user_id]['email']],
                        None,
                        template='mail/tour_expire',
                        notifications=notifications[user_id],
                        user=user
                    )
                log.info('Отправлено письмо "{}" на {}'.format(subj, user.email))

