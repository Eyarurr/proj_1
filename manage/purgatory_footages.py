import os
import json
import logging

import shutil
from flask import current_app
from sqlalchemy import inspect

from visual.models import Footage
from visual.core import db
from visual.app import CustomJSONEncoder


log = logging.getLogger(__name__)


def object_as_dict(obj):
    return {c.key: getattr(obj, c.key)
            for c in inspect(obj).mapper.column_attrs}


class PurgeFootages:
    """Убирает неиспользуемые съёмки в PURGATORY_DIR и стирает их за ненадобностью через 2 недели"""
    def run(self, loglevel=None, dry=False):
        log.setLevel(loglevel)
        footages = Footage.query.filter(~Footage.tours.any()).order_by(Footage.id.desc()).all()

        log.info('Перемещаем неиспользуемые съемки: {} шт.'.format(footages))

        for footage in footages:
            log.info('Перемещаем съёмку #{} updated={}'.format(footage.id, footage.updated))

            if not dry:
                obj = object_as_dict(footage)
                dst = os.path.join(current_app.config['PURGATORY_DIR'], 'footages', str(footage.id))
                try:
                    if footage.files:
                        shutil.move(footage.in_files(), dst)

                    os.makedirs(dst, exist_ok=True)
                    with open(os.path.join(dst, '_footage.json'), 'w') as outfile:
                        json.dump(obj, outfile, cls=CustomJSONEncoder)
                except (FileExistsError, OSError) as e:
                    log.error('Ошибка копирования и записи файлов съемки #{}: {}'.format(str(footage.id), str(e)))
                else:
                    footage.delete()
                    db.session.commit()
