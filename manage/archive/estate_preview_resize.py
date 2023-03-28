import logging

from flask_script import Command
from sqlalchemy import or_, Integer

from visual.models import Estate
from visual.core import db


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)


class EstatePreviewResize(Command):
    def __init__(self, func=None):
        super().__init__(func)

    def run(self):
        estates = db.session.query(Estate).filter(or_(Estate._assets['preview']['width'].astext.cast(Integer) < Estate.preview.width,
                                                      Estate._assets['preview']['height'].astext.cast(Integer) < Estate.preview.height)).all()
        for estate in estates:
            try:
                estate.preview = estate.tours[0].screen.abs_path
            except IndexError:
                log.warning("У Estate id={} нет тура".format(estate.id))
        db.session.commit()
