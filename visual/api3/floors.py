"""
API этажей туров.
"""

import os
import shutil

from flask import request, current_app, abort
from flask_login import login_required
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified

from . import mod, api_response
from visual.models.meta import FootageMetaInside, Floor
from ..core import db
from visual.util import downsize_img, get_flow_file, coerce_str_i18n
from .common import load_footage_edit


def _get_size(val):
    """Проверяет тип свойства тела запроса с размером и возвращает его в виде списка [int, int]"""
    try:
        size = (int(val[0]), int(val[1]))
    except (KeyError, ValueError, TypeError):
        abort(400, gettext('Bad data type for property %(property)s', property='big@resize'))
    return size


def update_floor_from_api_request(floor, payload):
    """Обновляет Floor из payload апишного запроса.
    """
    warnings = []
    simple_props = {'title': coerce_str_i18n, 'scale': float, 'big': str, 'small': str}
    skip_props = {'big@resize', 'small@resize'}

    for key, value in payload.items():
        if key in simple_props:
            if value is None:
                setattr(floor, key, None)
            else:
                try:
                    setattr(floor, key, simple_props[key](value))
                except (ValueError, TypeError):
                    abort(400, gettext('Bad data type for property %(property)s', property=key))

        elif key == 'offset':
            if value is None:
                floor.offset = None
            else:
                try:
                    floor.offset = [float(value[0]), float(value[1])]
                except (ValueError, TypeError, KeyError):
                    abort(400, gettext('Bad data type for property %(property)s', property=key))

        elif key == 'big@flow':
            if value is None:
                floor.delete_files()
                floor.big = None
                floor.small = None
            else:
                src, _, _ = get_flow_file(payload, 'big@flow')
                filename, ext = os.path.splitext(src)

                os.makedirs(floor.meta.footage.in_files('maps'), exist_ok=True)
                dst_filename = floor.gen_plan_filename('big', ext)
                floor.delete_files()
                dst = floor.meta.footage.in_files('maps', dst_filename)

                if 'big@resize' in payload:
                    downsize_img(src, dst, _get_size(payload['big@resize']), 'fit', True)
                else:
                    shutil.copy(src, dst)

                floor.big = 'maps/' + dst_filename

                if 'small@resize' in payload:
                    dst_filename = floor.gen_plan_filename('small', ext)
                    dst = floor.meta.footage.in_files('maps', dst_filename)

                    downsize_img(src, dst, _get_size(payload['small@resize']), 'fit', True)
                    floor.small = 'maps/' + dst_filename

        elif key not in skip_props:
            warnings.append(gettext('Unknown input property %(property)s', property=key))

    return warnings


@mod.route('/footages/<int:footage_id>/virtual/floors/<floor_id>', methods=('PUT', ))
@login_required
def put_footage_floor(footage_id, floor_id):
    """
    PUT /footages/<footage_id>/virtual/floors/<floor_id>
    Input:
        {
            "big@flow": "TOKEN/filename",
            "big@resize": [int, int],
            "small@resize": [int, int],
            "title": str,
            "offset": [float, float],
            "scale": float
        }
    Output:
        Floor
    """
    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'), required_statuses=('testing', 'loading', 'published'))
    meta = FootageMetaInside(footage)

    if floor_id not in meta.floors:
        meta.floors[floor_id] = Floor(meta, floor_id, {})

    warnings = update_floor_from_api_request(meta.floors[floor_id], request.json)

    footage.meta.setdefault('floors', {})
    footage.meta['floors'][floor_id] = meta.floors[floor_id].api_repr()
    flag_modified(footage, 'meta')
    db.session.commit()

    return api_response(footage.meta['floors'][floor_id], warnings=warnings)


@mod.route('/footages/<int:footage_id>/virtual/floors', methods=('PUT', ))
@login_required
def put_footage_floors(footage_id):
    """
    PUT /footages/<footage_id>/virtual/floors
    Изменяет несколько этажей. Несуществующие создаёт.
    Input:
        { floor_id: FloorRequest, ... }
    Output:
        FootageMetaInside.floors
    """
    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'), required_statuses=('testing', 'loading', 'published'))

    meta = FootageMetaInside(footage)

    floors = footage.meta.setdefault('floors', {})
    warnings = []
    for floor_id, floor_request in request.json.items():
        if floor_id not in meta.floors:
            meta.floors[floor_id] = Floor(meta, floor_id, {})
        warnings += update_floor_from_api_request(meta.floors[floor_id], floor_request)
        floors[floor_id] = meta.floors[floor_id].api_repr()

    footage.meta['floors'] = floors
    flag_modified(footage, 'meta')
    db.session.commit()

    return api_response(floors, warnings=warnings)


@mod.route('/footages/<int:footage_id>/virtual/floors/<floor_id>', methods=('DELETE', ))
@login_required
def delete_footage_floor(footage_id, floor_id):
    """
    DELETE /footages/<footage_id>/virtual/floors/<floor_id>
    """
    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'), required_statuses=('testing', 'loading', 'published'))

    meta = FootageMetaInside(footage)

    for skybox in meta.skyboxes.values():
        if str(skybox.floor) == floor_id:
            abort(404, gettext('Floor %(floor_id)s cannot be deleted', floor_id=floor_id))

    if floor_id not in meta.floors:
        abort(404, gettext('Floor %(floor_id)s not found.', floor_id=floor_id))
    else:
        if len(meta.floors) == 1:
            abort(404, gettext('Deleting first floor is not allowed, tour should always have at least a single floor'))


    meta.floors[floor_id].delete_files()
    del footage.meta['floors'][floor_id]
    flag_modified(footage, 'meta')
    db.session.commit()

    return '', 204


@mod.route('/footages/<int:footage_id>/virtual/floor_heights', methods=('PUT', ))
@login_required
def put_virtual_floor_heights(footage_id):
    """
    Input:
        { floor_id: floor_height, ... }
    Output:
        {}
    """
    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'), required_statuses=('testing', 'loading', 'published'))


    if '_loading' not in footage.meta:
        abort(400, gettext('Wrong tour status.'))

    floor_heights = {}
    for k, v in request.json.items():
        try:
            floor_heights[k] = float(v)
        except ValueError:
            abort(400, gettext('Bad height for floor %(floor)s.', floor=k))

    footage.meta['_loading']['floor_heights'] = floor_heights

    for skybox_id, skybox in footage.meta['skyboxes'].items():
        if 'pos' not in skybox:
            continue
        for floor_id, height in floor_heights.items():
            if height >= 0:
                max_floor = max(map(int, floor_heights.keys()))
                max_height = max([h for h in floor_heights.values()])

                if skybox['pos'][2] > max_height:
                    skybox['floor'] = int(max_floor)
                    break
                if 0 <= skybox['pos'][2] <= height:
                    skybox['floor'] = int(floor_id)
                    break

            if height < 0:
                if 0 > skybox['pos'][2] > height:
                    skybox['floor'] = int(floor_id)
                    break

    flag_modified(footage, 'meta')
    db.session.commit()

    return '', 204


@mod.route('/footages/<int:footage_id>/floors/<floor_id>/minimap', methods=('DELETE',))
def delete_footage_floor_minimap(footage_id, floor_id):
    """
    Удаляет картинки планировок этажа, но сам этаж не трогает
    DELETE /footages/<int:footage_id>/floors/<floor_id>/minimap
    :return: 204
    """
    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'),
                                required_statuses=('testing', 'published'))

    meta = FootageMetaInside(footage)
    if floor_id not in meta.floors:
        abort(404, gettext('Floor %(floor_id)s not found.', floor_id=floor_id))

    meta.floors[floor_id].delete_files()
    for field in ('big', 'small', 'offset', 'scale'):
        footage.meta['floors'][floor_id].pop(field, None)
    flag_modified(footage, 'meta')
    db.session.commit()

    return '', 204