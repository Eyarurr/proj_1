import os
import shutil
import logging

from flask import current_app
from flask_script import Command, Option
from sqlalchemy.orm.attributes import flag_modified

from visual.models import Footage, Tour
from visual.core import db
from .progress import Progress
from visual.util import dict_merge


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)

progress = Progress()


def _move_tour_footage(what, src, dst, dry=False):
    """Копирует директорию или файл what из src в dst, где src и dst - Tour или Footage"""
    if dry:
        if not os.access(src.in_files(what), os.R_OK):
            raise FileNotFoundError('Нет доступа к %s' % src.in_files(what))
        print('Move {} -> {}'.format(src.in_files(what), dst.in_files(what)))
    else:
        if not os.access(src.in_files(what), os.R_OK):
            print('WARNING: В {} {} не удалось найти файл {}'.format(src.__class__.__name__, src.id, src.in_files(what)))
        else:
            os.rename(src.in_files(what), dst.in_files(what))


class Refactor2(Command):
    """
    Второй Великий Рефакторинг: переход к модели Footage->Tour
    """
    option_list = (
        Option('action', help='revert, если нужно откатить изменения', nargs='?'),
    )

    def cleanup(self):
        # Если были какие-то footages, то возвращаем содержимое их ассетов в tours и
        # мержим meta обратно
        footages = db.session.query(Footage, Tour).join(Tour).all()
        progress.action('Очищаем footages', len(footages))
        for footage, tour in footages:
            dict_merge(tour.meta, footage.meta)
            flag_modified(tour, 'meta')
            for what in os.listdir(footage.files.abs_path):
                _move_tour_footage(what, footage, tour)
            progress.step()

        Tour.query.update({'footage_id': None})
        db.session.commit()
        db.session.execute("DELETE FROM footages; SELECT setval('footages_id_seq', 1, false)")
        shutil.rmtree(os.path.join(current_app.config['ASSET_STORAGE_ROOT'], 'footages'), ignore_errors=True)
        db.session.commit()

    def run(self, action=None):
        self.cleanup()

        if action == 'revert':
            return

        tours = Tour.query.order_by(Tour.id).all()

        progress.action('Переносим данные из Tour в Footage', len(tours))
        for tour in tours:
            try:
                footage = Footage(
                    created=tour.created, estate_id=tour.estate_id, type=tour.type,
                    _status=tour.status
                )

                # Переносим, что нужно, из tour.meta
                footage.meta = {}

                if tour.status in ('loading', 'processing'):
                    # Мету для туров в состоянии загрузки и сборки копируем целиком
                    footage.meta = tour.meta
                    tour.meta = {}
                else:
                    # Свойства, которые тупо копируются
                    for prop in ('model', 'mtl', 'model_format', 'model_size', 'model_size_gz',
                                 'resolutions', 'passways', 'binocular'):
                        if prop in tour.meta:
                            footage.meta[prop] = tour.meta[prop]
                            del tour.meta[prop]

                    if tour.status == 'testing' and 'sources' in tour.meta:
                        footage.meta['sources'] = tour.meta['sources']
                        del tour.meta['sources']

                    # Из Tour.meta.skyboxes берём только некоторые свойства
                    footage.meta['skyboxes'] = {}
                    for skybox_id, skybox in tour.meta['skyboxes'].items():
                        footage.meta['skyboxes'][skybox_id] = {}
                        for prop in ('floor', 'pos', 'q', 'disabled', 'markerZ', 'revision'):
                            if prop in skybox:
                                footage.meta['skyboxes'][skybox_id][prop] = skybox[prop]
                                del skybox[prop]

                    # Из Tour.meta.floors берём только некоторые свойства
                    footage.meta['floors'] = {}
                    for floor_id, floor in tour.meta['floors'].items():
                        footage.meta['floors'][floor_id] = {}
                        for prop in ('big', 'small'):
                            if prop in floor:
                                footage.meta['floors'][floor_id][prop] = floor[prop]
                                del floor[prop]

                db.session.add(footage)
                db.session.flush()

                # Перемещаем, что нужно, из ассетов
                footage.mkdir()

                if tour.status in ('loading', 'processing'):
                    # Здесь переносим всю директорию ассета files
                    for folder in os.listdir(tour.files.abs_path):
                        _move_tour_footage(folder, tour, footage)
                else:
                    # А для обычных туров — только директории с разрешениями, maps и models
                    for folder in footage.meta['resolutions'] + ['maps', 'models']:
                        _move_tour_footage(str(folder), tour, footage)
                    if tour.status == 'testing':
                        _move_tour_footage('sources', tour, footage)

                # Привязываем tour к footage
                tour.footage_id = footage.id
                flag_modified(tour, 'meta')
                db.session.commit()
                progress.step()
            except Exception:
                print('\nException at tour %d' % tour.id)
                raise


        progress.end_action()
        progress.end()

