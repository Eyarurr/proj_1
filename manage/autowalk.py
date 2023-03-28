from sqlalchemy.orm.attributes import flag_modified

from visual.models import Tour
from visual.core import db


class AutoWalk:
    """Создаёт маршрут по всем точкам тура."""
    def run(self, tour_id, overwrite, delay):
        tour = Tour.query.get(tour_id)
        if not tour:
            print('Тур id={} не найдена'.format(tour_id))
            return

        if 'walk' in tour.meta and not overwrite:
            print('В туре уже есть маршрут. Запустите с опцией --overwrite, чтобы перезаписать его.')
            return

        tour.meta['walk'] = []

        for skybox_id, skybox in tour.footage.meta['skyboxes'].items():
            tour.meta['walk'].append({
                'action': 'goto',
                'duration': 300,
                'skybox': skybox_id,
                'q': [0, 0, 0, 1]
            })
            tour.meta['walk'].append({
                'action': 'pause',
                'duration': delay * 1000
            })

        flag_modified(tour, 'meta')
        db.session.commit()
