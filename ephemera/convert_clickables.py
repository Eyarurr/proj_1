import numpy as np
import quaternion
import math

from visual.models import Tour
from visual.core import db
from sqlalchemy.orm.attributes import flag_modified


"""
Скрипт конвертирует все Clickable в Overlay и выносит Action в словарь Tour.meta.actions.
"""

DEFAULTS = {
    'tooltip': '',
    'actions': None,
    'hidden': False,
    'q': [0, 0, 0, 1],
    'perspective': True,
    'billboardmode': False,
    'font': {
        'family': 'sans-serif',
        'size': None,
        'align': 'center',
        'color': [0, 0, 0, 1],
        'bold': False,
        'italic': False,
        'outline': None
    },
    'bar': {
        'aspect_ratio': None,
        'padding': 0,
        'color': [0, 0, 0, 0],
        'border': None
    },
    'size': 0.512
}


def magnitude(v):
    return math.sqrt(sum(v[n]*v[n] for n in range(len(v))))


def sub(u, v):
    return [u[n]-v[n] for n in range(len(u))]


def dot(u, v):
    return sum(u[n]*v[n] for n in range(len(u)))


def normalize(v):
    vmag = magnitude(v)
    return [v[n]/vmag for n in range(len(v))]


def read_vector(v):
    return [v[0], v[2], -v[1]]


def calc_q(pos, intersect, tour_id, clickable_id):
    if pos == intersect:
        print("В туре %s совпадают pos и intersect. Clickable id: %s" % (tour_id, clickable_id))
        return [0, 0, 0, 1]

    pos = read_vector(pos)
    intersect = read_vector(intersect)
    normal = normalize(sub(pos, intersect))
    from_ = [0, 0, 1]
    to = normal

    def set_from_vectors(from_, to):
        eps = 0.000001
        r = dot(from_, to) + 1

        if r < eps:
            r = 0
            if math.fabs(from_[0]) > math.fabs(from_[2]):
                v1 = [-from_[1], from_[0], 0]
            else:
                v1 = [0, -from_[2], from_[1]]
        else:
            v1 = np.cross(np.array(from_), np.array(to))

        _x = v1[0]
        _y = v1[1]
        _z = v1[2]
        _w = r
        return [_w, _x, _y, _z]

    _q = set_from_vectors(from_, to)
    _q = np.quaternion(_q[0], _q[1], _q[2], _q[3]).normalized()

    return [_q.x+0, _q.z+0, -_q.y+0, _q.w+0]


tours = db.session.query(Tour).all()

for tour in tours:
    if 'clickable' in tour.meta or 'toolbar' in tour.meta:
        if tour.meta.get('clickable', False):
            tour.meta['overlays'] = {}
        tour.meta['actions'] = {}
    else:
        continue

    id_ = '0'
    active_meshes = []

    for i, clickable in enumerate(tour.meta.get('clickable', [])):
        if clickable['type'] == 'mesh':
            active_meshes.append(clickable)
            continue
        widget = {}
        perspective = clickable.get('perspective', False)

        if clickable.get('intersect', False) and clickable.get('fixed_orientation', False):
            q = calc_q(clickable['pos'], clickable['intersect'], tour.id, i + 1)
        else:
            q = [0, 0, 0, 1]

        label = clickable.get('label', {})
        if label and label.get('text', ''):
            widget = {
                'text': label.get('text', ''),
                'pos': clickable['pos'],
                'q': q,
                'perspective': clickable.get('perspective', False),
                'billboardmode': not clickable.get('fixed_orientation', False),
                'font': {
                    'family': label.get('font_family', 'sans-serif'),
                    'size': label.get('font_size', 34)*0.8533/200 if perspective else label.get('font_size', 34)*0.9*4/200,
                    'align': label.get('text_align', 'center'),
                    'color': label.get('font_color', [0, 0, 0, 1]),
                    'bold': label.get('font_weight', False),
                    'italic': label.get('font_italic', False),
                    'outline': {
                        'width': label.get('font_stroke_width', 0),
                        'color': label.get('font_stroke_color', [0, 0, 0, 0])
                    }
                },
                'bar': {
                    # 'aspect_ratio': label.get('aspect_ratio', 1),
                    'padding': int(label.get('padding', 0)) / 200,
                    'color': label.get('bg_color', [0, 0, 0, 0]),
                    'border': {
                        'color': label.get('border_color', [0, 0, 0, 0]),
                        'width': int(label.get('border_width', 0)/200),
                        'radius': 0
                    }
                }
            }
            if label.get('aspect_ratio', None):
                widget['bar']['aspect_ratio'] = label['aspect_ratio']

            for k, v in dict(widget).items():
                if k == 'text' and v == '':
                    print("В туре %s text = ''. Clickable id: %s" % (tour.id, i+1))
                if k == 'pos' and v == [0, 0, 0, 0]:
                    print("В туре %s pos = [0, 0, 0, 0]. Clickable id: %s" % (tour.id, i+1))
                if k == 'font':
                    for p in list(dict(widget['font']).keys()):
                        if 'outline' in widget['font']:
                            outline = widget['font']['outline']
                            if p == 'outline' and outline['width'] == 0 and outline['color'] == [0, 0, 0, 0]:
                                widget['font']['outline'] = None
                            elif p == 'outline' and outline['width'] == 0:
                                outline.pop('width')
                            elif p == 'outline' and outline['color'] == [0, 0, 0, 0]:
                                outline.pop('color')

                        if widget['font'][p] == DEFAULTS['font'][p]:
                            widget['font'].pop(p)

                if k == 'bar':
                    for p in list(dict(widget['bar']).keys()):
                        if 'border' in widget['bar']:
                            border = widget['bar']['border']
                            if p == 'border' and border['color'] == [0, 0, 0, 0] and border['width'] == 0 and border['radius'] == 0:
                                widget['bar']['border'] = None
                            elif p == 'border' and border['color'] == [0, 0, 0, 0]:
                                border.pop('color')
                            elif p == 'border' and border['width'] == 0:
                                border.pop('width')
                            elif p == 'border' and border['radius'] == 0:
                                border.pop('radius')

                        if widget['bar'][p] == DEFAULTS['bar'][p]:
                            widget['bar'].pop(p)

                if k in DEFAULTS and v == DEFAULTS[k]:
                    widget.pop(k)
        else:
            if clickable.get('img'):
                if isinstance(clickable['img'], str):
                    url = clickable['img']
                elif isinstance(clickable['img'], list):
                    url = clickable['img'][0]
                else:
                    url = ''

            if perspective:
                # size = (clickable.get('size', 0) * 4 / 66.40625 or 0.512)
                size = (clickable.get('size', 0) / 66.40625 or 0.512)
            else:
                size = (clickable.get('size', 0) / 66.40625 or 0.512)

            widget = {
                # 'preset': clickable['img'] if isinstance(clickable['img'], int) else '',
                # 'url': url,
                # 'url_hover': clickable['img'][1] if isinstance(clickable['img'], list) else '',
                'size': size,
                'pos': clickable['pos'],
                'q': q,
                'perspective': clickable.get('perspective', False),
                'billboardmode': not clickable.get('fixed_orientation', False)
            }

            for k, v in dict(widget).items():
                if k == 'pos' and v == [0, 0, 0, 0]:
                    print("В туре %s pos = [0, 0, 0, 0]. Clickable id: %s" % (tour.id, i+1))
                if k in DEFAULTS and v == DEFAULTS[k]:
                    widget.pop(k)

            if clickable.get('img'):
                if isinstance(clickable['img'], int):
                    widget['preset'] = clickable['img']
                elif isinstance(clickable['img'], list):
                    widget['url'] = clickable['img'][0]
                    widget['url_hover'] = clickable['img'][1]
                else:
                    widget['url'] = clickable['img']
            else:
                widget['preset'] = 1

            # костыльный тип switch
            if clickable['type'] == 'switch':
                if clickable.get('init', None):
                    widget['init'] = clickable['init']

        id_ = str(i+1)
        tour.meta['overlays'][id_] = {
            'type': 'text' if clickable.get('label', {}).get('text', False) else 'image',
            'tooltip': clickable.get('title', ''),
            'widget': widget,
        }

        if clickable.get('class', ''):
            tour.meta['overlays'][id_]['class'] = [clickable['class']]

        # костыльный тип switch
        if clickable['type'] == 'switch':
            tour.meta['overlays'][id_]['type'] = 'switch'
            tour.meta['overlays'][id_]['actions'] = {'click': id_}
            tour.meta['actions'][id_] = {
                'type': 'switch'
            }
            if clickable.get('on', None):
                tour.meta['actions'][id_]['on'] = clickable['on']
            if clickable.get('off', None):
                tour.meta['actions'][id_]['off'] = clickable['off']

        for k, v in dict(tour.meta['overlays'][id_]).items():
            if k in DEFAULTS and v == DEFAULTS[k]:
                tour.meta['overlays'][id_].pop(k)

        if 'action' in clickable:
            tour.meta['overlays'][id_]['actions'] = {'click': id_}
            if 'blank' in clickable['action'].get('href', {}):
                del clickable['action']['href']['blank']
                clickable['action']['href']['target'] = '_blank'

            tour.meta['actions'][id_] = clickable['action']

    if 'toolbar' in tour.meta:
        for i, button in enumerate(tour.meta['toolbar']):
            if button.get('action', False):
                id_ = str(int(id_) + i + 1)
                tour.meta['actions'][id_] = button['action']
                button.pop('action')
                button['actions'] = {'click': id_}

    if active_meshes:
        tour.meta['active_meshes'] = {}

    for i, mesh in enumerate(active_meshes):
        if mesh.get('action', False):
            id_ = str(int(id_) + i + 1)
            tour.meta['actions'][id_] = mesh['action']
            mesh.pop('action')
            mesh['actions'] = {'click': id_}
        tour.meta['active_meshes'][mesh['object_id']] = mesh
        mesh.pop('object_id')

    if 'clickable' in tour.meta:
        del tour.meta['clickable']

    flag_modified(tour, 'meta')
db.session.commit()
