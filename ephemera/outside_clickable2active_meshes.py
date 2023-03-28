import copy

from visual.models import Tour, Footage
from visual.core import db
from sqlalchemy.orm.attributes import flag_modified
from pprint import pprint


tours = Tour.query.join(Footage) \
            .filter(Footage.type == 'outside') \
            .order_by(Tour.id.desc()) \
            .all()

for tour in tours:
    active_meshes = []
    actions = {}
    mesh_id = 0

    for k, v in tour.meta.get('sets', {}).items():
        if v.get('clickable', []):
            v['active_meshes'] = {}

            for i, clickable in enumerate(copy.deepcopy(v.get('clickable', []))):
                if clickable['type'] == 'mesh':
                    mesh_id = mesh_id+1

                    actions[str(mesh_id)] = clickable['action']

                    clickable['actions'] = {'click': str(mesh_id)}
                    if (clickable.get('title')):
                        clickable['tooltip'] = clickable.get('title')

                    clickable.pop('action')
                    clickable['look'] = {
                        'fill': clickable['color']
                    }
                    clickable['hover'] = {
                        'fill': [clickable['color'][0], clickable['color'][1], clickable['color'][2], 0.5],
                    }
                    clickable.pop('color')
                    v['active_meshes'][clickable['object_id']] = clickable
                    clickable.pop('object_id')
                    clickable.pop('title')
                    clickable.pop('type')

        v.pop('clickable', None)

    if (actions != {}):
        tour.meta['actions'] = actions
    flag_modified(tour, 'meta')
    if mesh_id > 0:
        print('Tour id #{} done!'.format(tour.id))

db.session.commit()