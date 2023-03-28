# Убирает из TourSkybox.title весь HTML

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sqlalchemy.orm.attributes import flag_modified
from visual import create_app
from visual.core import db
from visual.models import Tour, Footage


app = create_app('config.local.py')


with app.app_context():
    table = {
        '<br>': '\n',
        '<sup>2</sup>': '²',
        '<sup>2</sup3>': '²',
        '&sup2;': '²',
    }
    q = Tour.query.join(Footage).filter(Footage.type.in_(['real', 'virtual']))
    for tour in q.all():
        if 'skyboxes' not in tour.meta:
            continue
        for box_id, box in tour.meta['skyboxes'].items():
            if 'title' not in box:
                continue

            dirty = False

            if isinstance(box['title'], dict):
                for k, v in box['title'].items():
                    if '<' in v or '&' in v:
                        for orig, tr in table.items():
                            box['title'][k] = box['title'][k].replace(orig, tr)
                        dirty = True

            elif '<' in box['title'] or '&' in box['title']:
                for orig, tr in table.items():
                    box['title'] = box['title'].replace(orig, tr)
                dirty = True

        if dirty:
            flag_modified(tour, 'meta')

    db.session.commit()
