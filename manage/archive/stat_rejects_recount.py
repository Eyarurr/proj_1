import logging
from datetime import timedelta

from visual.core import db
from visual.models import StatSession
from manage import StatAggregate


class StatRejectsRecount:
    def run(self, from_date, to_date):
        self.log = logging.getLogger('statistics')
        rejections = db.session.query(StatSession). \
            order_by(StatSession.start, StatSession.time_in_session).all()
        session_dict = {}
        for session in rejections:
            session_key = '{}-{}-{}-{}'.format(session.ip,
                                               session.tour_id,
                                               session.user_agent,
                                               session.start.strftime("%Y/%m/%d"))
            real_session = session_dict.get(session_key)
            if real_session is None:
                session_dict[session_key] = session
            elif session.start - real_session.start - real_session.time_in_session < timedelta(minutes=30):
                self.log.info("Session {} in {} deleted.".format(session.ip, session.start))
                real_session.time_in_session = session.start - real_session.start + session.time_in_session
                db.session.delete(session)
            else:
                session.is_uniq = None
                session_dict[session_key] = session
        db.session.commit()
        StatAggregate().run(updated_tables=['count', 'time', 'city', 'referer'],
                            interval=from_date + '...' + to_date)


class StatClearing:
    def run(self):
        # Удаляем стату с ботами
        query = """DELETE FROM stat_sessions
                   WHERE user_agent ILIKE '%bot%' or user_agent ILIKE '%+http%';"""
        db.session.execute(query)
        db.session.commit()
        # Удаляем внутренний трафик
        query = """DELETE FROM stat_sessions WHERE ip = '185.11.49.158';"""
        db.session.execute(query)
        db.session.commit()
        # Удаляем дубли с хитами без кук
        StatRejectsRecount().run()
