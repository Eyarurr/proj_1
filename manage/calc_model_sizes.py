import logging
import colors

from sqlalchemy.orm.attributes import flag_modified

from visual.models import Footage
from visual.core import db
from .progress import Progress


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)

progress = Progress()


class CalcModelSizes:
    """Считает размеры моделей для всех туров."""

    def run(self):
        footages = Footage.query.order_by(Footage.id).all()
        progress.action('Считаем размеры моделей во всех съёмках', len(footages))

        for footage in footages:
            if 'model' not in footage.meta:
                print(colors.red('В съёмке {} нет модели!!!'.format(footage.id)))
            footage.meta['model_size_gz'], footage.meta['model_size'] = footage.get_gz_size()
            flag_modified(footage, 'meta')
            db.session.commit()
            progress.step()

        progress.end()
