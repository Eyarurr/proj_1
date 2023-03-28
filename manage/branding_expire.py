import logging
from datetime import datetime

from flask import current_app

from visual.models import TourPaidFeature, Tour, User
from visual.mail import send_email
from visual.core import db

log = logging.getLogger(__name__)


class BrandingExpire:
    """
    Рассылает пользователям уведомления об окончании срока подписки на брендинг, если осталось кол-во дней,
    указанных в BRANDING_EXPIRE_NOTIFICATIONS.
    """
    def run(self, quiet=False, dry=False, loglevel=logging.WARNING):
        log.setLevel(loglevel)

        branding_xdays = current_app.config.get('BRANDING_EXPIRE_NOTIFICATIONS')
        notifications = {}

        q = db.session.query(TourPaidFeature, Tour)\
            .join(Tour, Tour.id==TourPaidFeature.tour_id)\
            .filter(TourPaidFeature.feature=='branding')\
            .order_by(TourPaidFeature.tour_id.desc())\

        for tour_paid_feature, tour in q.all():
            tour_xday = (tour_paid_feature.paid_till - datetime.now(tz=tour_paid_feature.paid_till.tzinfo)).days

            if tour_xday in branding_xdays and tour.user.email_notifications:
                if tour.user_id not in notifications:
                    notifications[tour.user_id] = {'notify': {}, 'email': tour.user.email}
                if tour_xday not in notifications[tour.user_id]['notify']:
                    notifications[tour.user_id]['notify'][tour_xday] = []
                notifications[tour.user_id]['notify'][tour_xday].append(
                    (tour.id, tour.title, tour.user_id)
                )
                if not quiet:
                    log.info('NOTIFY branding для тура {0.title}, id {0.id}, осталось {1} дн. ({2})'.format(tour, tour_xday, tour.user.email))

        if not dry:
            for user_id in notifications.keys():
                user = User.query.get(user_id)
                send_email(
                    'Tour(s) branding expires soon',
                    [notifications[user_id]['email']],
                    None,
                    template='mail/branding_expire',
                    notifications=notifications[user_id],
                    user=user, price=current_app.config['PAID_FEATURES']['branding']['price']
                )
