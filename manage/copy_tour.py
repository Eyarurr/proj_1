from sqlalchemy.orm.attributes import flag_modified

from visual.models import Folder, Tour, Footage
from visual.core import db
from visual.bgjobs import BgJobState
from .progress import Progress


class CopyTour:
    """Копирует туры и съёмки"""
    def run(self, tour_id, title, folder_id=None, copy_footage=False, copy_meta=False, created_by=None, quiet=False):
        if quiet:
            self.bgstate = BgJobState('tour-copy', tour_id, 'processing')
        else:
            self.bgstate = None
        self.progress = Progress(quiet=quiet, bgstate=self.bgstate)

        tour = Tour.query.options(db.joinedload(Tour.footage)).get(tour_id)
        if not tour:
            self.progress.error('Тур id={} не найден.'.format(tour_id))
            return

        if folder_id and folder_id != '0':
            folder = Folder.query.filter_by(user_id=tour.user_id, id=folder_id).first()
            if not folder:
                self.progress.error('У этого пользователя нет папки id={}.'.format(folder_id))
                return

        if copy_footage:
            self.progress.action('Копируется съёмка')
            new_footage = Footage(
                type=tour.footage.type,
                _status=tour.footage.status,
                user_id=tour.user_id,
                meta=tour.footage.meta
            )
            if created_by:
                new_footage = created_by

            db.session.add(new_footage)
            db.session.flush()
            new_footage.files = tour.footage.files.abs_path
        else:
            new_footage = tour.footage

        self.progress.action('Копируется тур')
        newborn = Tour(
            footage_id=new_footage.id,
            user_id=tour.user_id,
            title=title,
            hidden=tour.hidden,
            meta={},
            gallery_user=tour.gallery_user
        )

        if folder_id is None:
            newborn.folder_id = tour.folder_id
        elif folder_id == '0':
            newborn.folder_id = None
        else:
            newborn.folder_id = folder_id

        if created_by:
            newborn.created_by = created_by

        db.session.add(newborn)
        db.session.flush()
        newborn.preview = tour.preview.abs_path
        newborn.screen = tour.screen.abs_path

        if copy_meta:
            newborn.meta = tour.meta.copy()
            newborn.files = tour.files.abs_path
        else:
            newborn.meta['start'] = tour.meta.get('start', {}).copy()
            flag_modified(newborn, 'meta')
            newborn.mkdir()

        db.session.commit()

        self.progress.end()

