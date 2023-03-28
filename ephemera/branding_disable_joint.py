"""
Правка меты: в options.disable добавляется joint, если у тура есть брендинг
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from visual import create_app
from visual.core import db
from visual.models import Footage, Tour, TourFeature

from sqlalchemy.orm.attributes import flag_modified

app = create_app('config.local.py')



with app.app_context():
    count = 0

    tours = Tour.query.join(TourFeature).\
        filter(TourFeature.feature == 'branding').\
        options(db.contains_eager(Tour.features)).all()

    for tour in tours:
        if 'branding' in tour.paid_features_time_left():
            count += 1
            meta = tour.meta
            if 'options' not in meta:
                meta['options'] = {'disable': ['joint']}
                #print(tour.title, meta['options'])
            else:
                if 'disable' in meta['options']:
                    if 'joint' not in meta['options']['disable']:
                        meta['options']['disable'].append('joint')
                        #print(tour.title, meta['options'])
                else:
                    meta['options']['disable'] = ['joint']
                    #print(tour.title, meta['options'])

            flag_modified(tour, 'meta')
    db.session.commit()
    print(count)



