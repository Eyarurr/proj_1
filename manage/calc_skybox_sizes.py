import logging
from sqlalchemy.orm.attributes import flag_modified

from visual.models import Tour, Footage
from visual.models.meta import FootageMetaInside
from visual.core import db


log = logging.getLogger(__name__)

class CalcSkyboxSizes:
    """Пересчитывает размеры файлов скайбоксов в FootageSkybox.files_sizes.
    """
    def run(self, **options):
        log.setLevel(options['loglevel'])

        query = Footage.query.filter(Footage.type.in_(['real', 'virtual'])).filter(Footage._status.in_(['testing', 'published', 'banned']))
        if len(options['footage_id']) > 1 or options['footage_id'][0] != 'all':
            log.debug('Считаем files_size для съёмок {}'.format(options['footage_id']))
            query = query.filter(Footage.id.in_(options['footage_id']))
        else:
            log.debug('Пересчитываем для всех съёмок')
        query = query.order_by(Footage.id)

        footages = query.all()
        log.info('Съёмок: {}'.format(len(footages)))

        for footage in query.all():
            meta = FootageMetaInside(footage)
            log.info('Footage {}'.format(footage.id))
            for skybox_id, skybox in meta.skyboxes.items():
                fs = skybox.files_size
                skybox.recalc_files_size()
                log.debug('  skybox {}'.format(skybox_id))
                log.debug('  old: {}'.format(fs))
                log.debug('  new: {}'.format(skybox.files_size))

            if not options['dry']:
                flag_modified(footage, 'meta')

        if not options['dry']:
            db.session.commit()
