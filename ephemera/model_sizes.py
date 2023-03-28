"""
Проходится по всем моделям и считает model_size, model_size_gz, если их нет
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sqlalchemy.orm.attributes import flag_modified
from visual import create_app
from visual.core import db
from visual.models import Footage

app = create_app('config.local.py')


with app.app_context():
    for footage in Footage.query.filter(Footage.type.in_(['real', 'virtual']), Footage._status.in_(['testing', 'published', 'banned'])).order_by(Footage.id.desc()):
        if 'model_size_gz' not in footage.meta or 'model_size' not in footage.meta:
            print('Считаем model_size для footage {}: {}, {}'.format(footage.id, footage.type, footage.status))
            footage.meta['model_size_gz'], footage.meta['model_size'] = footage.get_gz_size()
            flag_modified(footage, 'meta')
            db.session.commit()
