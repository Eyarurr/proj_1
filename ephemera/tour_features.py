"""
Пересчитывает фичи для всех туров.
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from visual import create_app
from visual.models import Tour, Footage
from visual.core import db

app = create_app('config.local.py')


with app.app_context():
    for tour in Tour.query.join(Footage).filter(Footage.type.in_(['virtual', 'real'])):
        print(tour.id, tour.save_features())

    db.session.commit()


