import os
import zipfile
import json

from flask_script import Command, Option

from visual.models import Tour
from visual.core import db
from .progress import Progress

progress = Progress()


class TourModelsExport(Command):
    """Экспортирует метаданные всех туров в zip-архив"""
    option_list = (
        Option('zip_file'),
    )

    def run(self, zip_file):
        tours = Tour.query.all()

        progress.action('Экспортируются model.json из всех туров в %s' % zip_file, len(tours))

        with zipfile.ZipFile(zip_file, 'w', compression=zipfile.ZIP_BZIP2) as zf:
            tour_titles = {}

            for tour in tours:
                model_path = os.path.join(tour.tour.abs_path, 'model.json')
                zf.write(model_path, '%d.json' % tour.id)
                progress.step()

                tour_titles[tour.id] = tour.title

            zf.writestr('titles.txt', json.dumps(tour_titles, ensure_ascii=False, indent=4), compress_type=zipfile.ZIP_BZIP2)

            progress.end_action()


class TourModelsImport(Command):
    """Импортирует метаданные в туры из zip-файла"""
    option_list = (
        Option('zip_file'),
    )

    def run(self, zip_file):
        progress.action('Импортируются model.json для всех туров из .zip')

        with zipfile.ZipFile(zip_file, 'r') as zf:
            titles = json.loads(zf.read('titles.txt').decode())

            for member in zf.infolist():
                if not member.filename.endswith('.json'):
                    continue

                tour_id = int(member.filename.split('.')[0])
                tour = Tour.query.get(tour_id)
                if not tour:
                    progress.error('Не удалось найти тур ID=%d' % tour_id)
                    continue
                if tour.title != titles[str(tour_id)]:
                    progress.warn('Название тура %d не совпадает! local:%s != remote:%s' % (tour_id, tour.title, titles[str(tour_id)]))

                target = os.path.join(tour.tour.abs_path, 'model.json')
                model = zf.read(member)
                with open(target, 'wb') as out:
                    out.write(model)

                db.session.commit()
