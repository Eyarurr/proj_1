"""
Проходится по всем турам, и если находит в их мете `floors', то переносит их в Footage
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sqlalchemy.orm.attributes import flag_modified
from visual import create_app
from visual.models import Tour, Footage
from visual.core import db

app = create_app('config.local.py')


with app.app_context():
    if len(sys.argv) > 1 and sys.argv[1] == 'go':
        dry = False
    else:
        dry = True

    for tour in Tour.query.options(db.joinedload(Tour.footage)).order_by(Tour.id).all():
        footage = tour.footage
        if 'floors' not in tour.meta:
            continue
        if 'floors' not in tour.footage.meta:
            print('Tour {} contains floors, Footage {} does not!'.format(tour.id, footage.id))
            continue

        for floor_id, floor in tour.meta['floors'].items():
            if floor_id not in footage.meta['floors']:
                print('Tour {} floor {}: exist in tour, does not exist in footage'.format(tour.id, footage.id))
                continue

            if not floor or 'title' not in floor or floor['title'] == '':
                continue

            if footage.meta['floors'][floor_id].get('title'):
                print('Tour {} floor {} title conflict: {!r} => {!r}'.format(tour.id, floor_id, floor['title'], footage.meta['floors'][floor_id]['title']))
            else:
                print('Tour {} floor {} title: {!r} => {!r}'.format(tour.id, floor_id, floor['title'], footage.meta['floors'][floor_id].get('title')))

            footage.meta['floors'][floor_id]['title'] = floor['title']
            flag_modified(footage, 'meta')

        tour.meta.pop('floors', None)
        flag_modified(tour, 'meta')

    if dry:
        print('Запустите {} go, чтобы аписать изменения в базу.'.format(sys.argv[0]))
    else:
        db.session.commit()
