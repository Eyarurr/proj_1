import logging
from flask_script import Command

from visual.models import StatSession
from visual.core import db
from .progress import Progress


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)

progress = Progress()


class StatParseUserAgents(Command):
    """Распарсивает строку User-Agent из лога статистики в поля device_*, os_*, browser_*"""
    def __init__(self, func=None):
        super().__init__(func)

    def run(self):
        sessions = StatSession.query.filter(StatSession.user_agent != None, StatSession.user_agent != '').all()
        progress.action('Перепарсиваем все user-agent в stat_sessions', len(sessions))
        cnt_delete = 0
        for sess in sessions:
            if not sess.parse_user_agent():
                db.session.delete(sess)
                cnt_delete += 1
            progress.step()

        db.session.commit()
        progress.end()
        print('Удалено сессий от ботов: {}'.format(cnt_delete))
