from visual.models import Tour, Footage
from visual.core import db
from sqlalchemy.orm.attributes import flag_modified
from pprint import pprint

tours = Tour.query.join(Footage) \
            .filter(Footage.type == 'virtual') \
            .order_by(Tour.id.desc()) \
            .all()

for tour in tours:
    for k, v in tour.meta.get('active_meshes', {}).items():
        if v.get('color'):
            v['hover'] = {'fill': v.get('color')}
            del tour.meta['active_meshes'][k]['color']
        if v.get('hide_cursor'):
            if v.get('hover'):
                v['hover'].update({'hide_cursor': v.get('hide_cursor')})
            else:
                v['hover'] = {'hide_cursor': v.get('hide_cursor')}
            del tour.meta['active_meshes'][k]['hide_cursor']
    if tour.meta.get('options'):
        if tour.meta['options'].get('clickable_fill_color'):
            tour.meta['options']['active_meshes_hover_fill'] = tour.meta['options']['clickable_fill_color']
            del tour.meta['options']['clickable_fill_color']

    flag_modified(tour, 'meta')

    print('Tour id #{} done!'.format(tour.id))
db.session.commit()
