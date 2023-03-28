import os
import json

from shutil import move
from flask import current_app
from sqlalchemy import exists

from visual.models import Footage, User
from visual.core import db

from .progress import Progress


class RessurectFootage:
    """Восстановление съемки по ID"""
    def run(self, footage_id):
        self.progress = Progress()
        src = os.path.join(current_app.config['PURGATORY_DIR'], 'footages', str(footage_id))

        if os.path.isdir(src):
            file_path = os.path.join(src, '_footage.json')
            if os.path.exists(file_path):
                try:
                    with open(file_path) as f:
                        data = json.load(f)
                        if data['created_by'] is not None:
                            user_exists = db.session.query(exists().where(User.id == data['created_by'])).scalar()
                            if not user_exists:
                                data['created_by'] = None
                except (OSError, FileNotFoundError) as e:
                    self.progress.error('Не могу загрузить json съемки: {}'.format(e))
                else:
                    footage = Footage(**data)
                    move(src, footage.in_files())
                    os.unlink(os.path.join(footage.in_files(), '_footage.json'))

                    db.session.add(footage)
                    db.session.commit()
                    self.progress.say('Съемка #{} восстановлена!'.format(str(footage_id)))
            else:
                self.progress.error('Неверный путь к файлу json съемки: {}'.format(file_path))
        else:
            self.progress.error('Неверный путь к директории съемки: {}'.format(src))
