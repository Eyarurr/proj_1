"""
API скайбоксов.
"""
from flask import request, current_app, g, abort
from flask_login import current_user, login_required
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified

from . import mod, api_response
from visual.models.meta import FootageMetaInside, FootageSkybox
from visual.util import unlink_calm, get_flow_file, coerce_str_i18n
from visual.core import queue_quick

from ..core import db
from .common import load_footage_edit, BgJob

QUEUE_WURST_HACKEN_TRESHOLD = 10

def update_skybox_from_api_request(skybox, payload):
    """Обновляет Skybox из payload апишного запроса.
    """
    warnings = []
    simple_props = {'floor': int, 'title': coerce_str_i18n, 'disabled': bool, 'markerZ': float}
    skip_props = ('wurst@eye', 'wurst@render_type', 'wurst@shadow')

    for key, value in payload.items():
        if key in simple_props:
            if value is None:
                setattr(skybox, key, None)
            else:
                try:
                    setattr(skybox, key, simple_props[key](value))
                except (ValueError, TypeError):
                    abort(400, gettext('Bad data type for property %(property)s', property=key))

        elif key == 'pos':
            try:
                skybox.pos = [float(payload['pos'][0]), float(payload['pos'][1]), float(payload['pos'][2])]
            except (ValueError, KeyError, TypeError, IndexError):
                abort(400, gettext('Bad data type for property %(property)s', property='pos'))

        elif key == 'q':
            try:
                skybox.q = [float(payload['q'][0]), float(payload['q'][1]), float(payload['q'][2]), float(payload['q'][3])]
            except (ValueError, KeyError, TypeError, IndexError):
                abort(400, gettext('Bad data type for property %(property)s', property='q'))

        elif key == 'shadows':
            try:
                newshadows = set(value)
            except TypeError:
                abort(400, gettext('Bad data type for property %(property)s', property='shadows'))

            if not skybox.shadows or set(skybox.shadows) != newshadows:
                abort(400, gettext('Shadows has been changed. Please reload the page.'))

            skybox.shadows = value

        elif key == 'wurst@flow':
            wurst, _, _ = get_flow_file(payload, 'wurst@flow')
            eye = payload.get('wurst@eye')
            shadow_id = payload.get('wurst@shadow')
            if shadow_id == '_':
                shadow_id = None
            if shadow_id is not None and shadow_id not in skybox.meta.shadows:
                abort(404, gettext('Shadow %(shadow_id)s not found.', shadow_id=shadow_id))
            if eye not in ('center', 'left', 'right', 'both'):
                abort(400, gettext('Invalid %(property)s value', property='wurst@eye'))
            render_type = payload.get('wurst@render_type', 'vray')
            if render_type not in ('vray', 'corona'):
                abort(400, gettext('Invalid %(property)s value', property='wurst@render_type'))
            try:
                skybox.wurst_hacken(wurst, eye, render_type, shadow=shadow_id)
            except ValueError as e:
                abort(400, str(e))
            unlink_calm(wurst)
        elif key not in skip_props:
            warnings.append(gettext('Unknown input property %(property)s', property=key))

    return warnings


@mod.route('/footages/<int:footage_id>/virtual/skyboxes/<skybox_id>', methods=('PUT', ))
@login_required
def put_footage_skybox(footage_id, skybox_id):
    """
    PUT /footages/<footage_id>/virtual/skyboxes/<skybox_id>
    Input:
        {
            "wurst@flow": "TOKEN/filename",
            "wurst@eye": "center" | "left" | "right" | "both"
            "wurst@render_type": "vray" | "corona",
            "pos": vertor3,
            "q": quaternion,
            "floor": str,
            "title": str,
            "disabled": bool,
            "audio": {},
            "markerZ": float
        }
    Output:
        FootageSkybox
    """
    footage = load_footage_edit(footage_id)
    meta = FootageMetaInside(footage)

    if skybox_id not in meta.skyboxes:
        meta.skyboxes[skybox_id] = FootageSkybox(meta, skybox_id, {})

    warnings = update_skybox_from_api_request(meta.skyboxes[skybox_id], request.json)

    footage.meta.setdefault('skyboxes', {})
    footage.meta['skyboxes'][skybox_id] = meta.skyboxes[skybox_id].api_repr()
    flag_modified(footage, 'meta')
    db.session.commit()

    return api_response(footage.meta['skyboxes'][skybox_id], warnings=warnings)


@mod.route('/footages/<int:footage_id>/virtual/skyboxes', methods=('PUT', ))
@login_required
def put_footage_skyboxes(footage_id):
    """
    PUT /footages/<footage_id>/virtual/skyboxes
    Изменяет несколько скайбоксов. Несуществующие создаёт.
    Input:
        { skybox_id: SkyboxRequest, ... }
    Output:
        FootageMetaInside.skyboxes
    """
    count_hacken = 0

    for skybox_request in request.json.values():
        if 'wurst@flow' in skybox_request:
            count_hacken += 1
    footage = load_footage_edit(footage_id)

    if count_hacken >= QUEUE_WURST_HACKEN_TRESHOLD:
        job = queue_quick.enqueue('visual.jobs.api.put_footage_skyboxes', footage.id, current_user.id, request.json)
        bgjob = BgJob(status='queued', id=job.id, queue_length=len(queue_quick)+1)
        return api_response({}, bgjobs=[bgjob.api_repr()])
    else:
        return process_many_skyboxes(footage, request.json)


def process_many_skyboxes(footage, payload):
    meta = FootageMetaInside(footage)

    skyboxes = footage.meta.setdefault('skyboxes', {})
    warnings = []
    for skybox_id, skybox_request in payload.items():
        if skybox_id not in meta.skyboxes:
            meta.skyboxes[skybox_id] = FootageSkybox(meta, skybox_id, {})
        warnings += update_skybox_from_api_request(meta.skyboxes[skybox_id], skybox_request)
        skyboxes[skybox_id] = meta.skyboxes[skybox_id].api_repr()

    footage.meta['skyboxes'] = skyboxes
    try:
        footage.meta['passways'] = footage.calc_passways()
    except Exception as e:
        warnings.append(gettext('Unable to process the model. Check if model is exported with Biganto tools and '
                                'reupload. Please contact technical support if problem persists.'))
        current_app.logger.error('Съёмка %d: плохая, плохая модель %s: %s' % (footage.id, footage.meta['model'], e))

    flag_modified(footage, 'meta')
    db.session.commit()

    return api_response(skyboxes, warnings=warnings)


@mod.route('/footages/<int:footage_id>/virtual/skyboxes/<skybox_id>', methods=('DELETE', ))
@login_required
def delete_footage_skybox(footage_id, skybox_id):
    footage = load_footage_edit(footage_id)
    meta = FootageMetaInside(footage)

    if skybox_id not in meta.skyboxes:
        abort(404, gettext('Skybox %(skybox_id)s not found.', skybox_id=skybox_id))

    meta.skybox_delete(skybox_id)

    # Удаляем скайбокс из туров съёмки
    for tour in footage.tours:
        if 'skyboxes' in tour.meta:
            tour.meta['skyboxes'].pop(skybox_id, None)
            flag_modified(tour, 'meta')

    footage.meta.setdefault('skyboxes', {})
    footage.meta['skyboxes'].pop(skybox_id, None)
    flag_modified(footage, 'meta')
    db.session.commit()

    return '', 204
