"""
API теней.
"""
import shutil
import logging

from flask import request, current_app, g, abort, render_template
from flask_login import current_user, login_required
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified
from email_validator import validate_email, EmailNotValidError
import jinja2
import json

from . import mod, api_response
from visual.models.meta import FootageMetaInside, Shadow
from visual.util import unlink_calm, get_flow_file
from visual.core import queue_quick
from ..core import db
from .common import load_footage_edit, load_tour_view, BgJob
from visual.mail import send_email


QUEUE_WURST_HACKEN_TRESHOLD = 10

def update_shadow_from_api_request(shadow, payload):
    """Обновляет Shadow из payload апишного запроса.
    """
    warnings = []
    simple_props = {'title': str, 'disabled': bool}
    skip_props = ()

    for key, value in payload.items():
        if key in simple_props:
            if value is None:
                setattr(shadow, key, None)
            else:
                try:
                    setattr(shadow, key, simple_props[key](value))
                except TypeError:
                    abort(400, gettext('Bad data type for property %(property)s', property=key))
        elif key == 'enter':
            try:
                shadow.enter = {
                    'effect': str(value['effect']),
                    'speed': float(value['speed'])
                }
            except (ValueError, KeyError, TypeError, IndexError):
                abort(400, gettext('Bad data type for property %(property)s', property='enter'))
            if shadow.enter['effect'] not in Shadow.EFFECTS:
                abort(400, gettext('Invalid effect "%(effect)s"', effect=shadow.enter['effect']))
        elif key == 'panoramas':
            if not isinstance(value, dict):
                abort(400, gettext('Bad data type for property %(property)s', property='panoramas'))

            if shadow.id == '_':
                abort(400, gettext('"_" shadow ID is reserved for default panoramas.'))

            for skybox_id, pandata in value.items():
                if skybox_id not in shadow.meta.skyboxes:
                    abort(404, gettext('Skybox %(skybox_id)s not found.', skybox_id=skybox_id))
                skybox = shadow.meta.skyboxes[skybox_id]

                wurst, _, _ = get_flow_file(pandata, 'wurst@flow')
                eye = pandata.get('wurst@eye')
                if eye not in ('center', 'left', 'right', 'both'):
                    abort(400, gettext('Invalid %(property)s value', property='wurst@eye'))
                render_type = pandata.get('wurst@render_type', 'vray')
                if render_type not in ('vray', 'corona'):
                    abort(400, gettext('Invalid %(property)s value', property='wurst@render_type'))
                try:
                    skybox.wurst_hacken(wurst, eye, render_type, shadow=shadow.id)
                except ValueError as e:
                    abort(400, str(e))

                if not skybox.shadows:
                    skybox.shadows = [shadow.id]
                elif shadow.id not in skybox.shadows:
                    skybox.shadows.append(shadow.id)
                unlink_calm(wurst)
        elif key == 'multichoice':
            if not isinstance(value, dict):
                abort(400, gettext('Bad data type for property %(property)s', property=key))

            shadows_multimenu = shadow.meta.get('shadows_multimenu', None)
            if shadows_multimenu:
                shadows_multimenu_ids = set([y['id'] for y in sum([x["contents"] for x in shadows_multimenu], [])])
                multichoice_values = set(value.values())
                if not multichoice_values.issubset(shadows_multimenu_ids):
                    abort(400, gettext('Invalid %(property)s value', property=key))
        elif key not in skip_props:
            warnings.append(gettext('Unknown input property %(property)s', property=key))

    return warnings


@mod.route('/footages/<int:footage_id>/virtual/shadows/<shadow_id>', methods=('PUT', ))
@login_required
def put_footage_shadow(footage_id, shadow_id):
    """
    PUT /footages/<footage_id>/virtual/shadows/<shadow_id>
    Input:
        {
            "title": str,
            "enter": { ... },
            "panoramas": {
                skybox_id: {
                    "wurst@flow": "TOKEN/filename",
                    "wurst@eye": "center" | "left" | "right" | "both",
                    "wurst@render_type": "vray" | "corona"
                ...
            }
                },
        }
    Output:
        Footage.shadows
    """
    count_hacken = 0

    for pano in request.json.get('panoramas', {}).values():
        if 'wurst@flow' in pano:
            count_hacken += 1
    footage = load_footage_edit(footage_id)

    if count_hacken >= QUEUE_WURST_HACKEN_TRESHOLD:
        job = queue_quick.enqueue('visual.jobs.api.put_footage_shadows', footage.id, shadow_id,
                                  current_user.id, request.json)
        bgjob = BgJob(status='queued', id=job.id, queue_length=len(queue_quick)+1)
        return api_response({}, bgjobs=[bgjob.api_repr()])
    else:
        return process_many_shadows(footage, shadow_id, request.json)


def process_many_shadows(footage, shadow_id, payload):
    meta = FootageMetaInside(footage)

    if shadow_id not in meta.shadows:
        meta.shadows[shadow_id] = Shadow(meta, shadow_id, {})

    warnings = update_shadow_from_api_request(meta.shadows[shadow_id], payload)

    footage.meta.setdefault('shadows', {})
    footage.meta['shadows'][shadow_id] = meta.shadows[shadow_id].as_dict()
    if meta.skyboxes:
        for box_id, skybox in meta.skyboxes.items():
            footage.meta['skyboxes'][box_id] = skybox.api_repr()
    flag_modified(footage, 'meta')
    for tour in footage.tours:
        tour.save_features()
    db.session.commit()

    return api_response(footage.meta['shadows'][shadow_id], warnings=warnings)


@mod.route('/footages/<int:footage_id>/virtual/shadows/<shadow_id>/<skybox_id>', methods=('DELETE', ))
@login_required
def delete_footage_shadow_skybox(footage_id, shadow_id, skybox_id):
    """
    DELETE /footages/<footage_id>/virtual/shadows/<shadow_id>/<skybox_id>
    Удаляет тень из скайбокса. Стирает панорамы.
    :param footage_id:
    :param shadow_id:
    :param skybox_id:
    :return:
    """
    footage = load_footage_edit(footage_id)
    meta = FootageMetaInside(footage)

    if shadow_id not in meta.shadows:
        abort(404, gettext('Shadow %(shadow_id)s not found.', shadow_id=shadow_id))

    if skybox_id not in meta.skyboxes:
        abort(404, gettext('Skybox %(skybox_id)s not found.', skybox_id=skybox_id))

    skybox = meta.skyboxes[skybox_id]

    if not skybox.shadows or shadow_id not in skybox.shadows:
        abort(404, gettext('There is no shadow %(shadow_id)s in skybox %(skybox_id)s.', shadow_id=shadow_id, skybox_id=skybox_id))

    skybox.shadows.remove(shadow_id)
    del skybox.files_size['shadows'][shadow_id]
    for res in meta.resolutions:
        for face in range(6):
            unlink_calm(footage.in_files('shadows', shadow_id, str(res), '{}-{}.jpg'.format(skybox_id, face)))

    footage.meta['skyboxes'][skybox_id] = skybox.api_repr()
    flag_modified(footage, 'meta')
    db.session.commit()

    return '', 204


@mod.route('/footages/<int:footage_id>/virtual/shadows/<shadow_id>', methods=('DELETE', ))
@login_required
def delete_footage_shadow(footage_id, shadow_id):
    """
    DELETE /footages/<footage_id>/virtual/shadows/<shadow_id>
    Удаляет тень.
    GET:
    - ?keep_definition: оставить определение тени в FootageMeta.shadows
    :return:
    """
    footage = load_footage_edit(footage_id)
    meta = FootageMetaInside(footage)

    if shadow_id not in meta.shadows:
        abort(404, gettext('Shadow %(shadow_id)s not found.', shadow_id=shadow_id))

    # Стираем тень из скайбоксов
    for skybox_id, skybox in meta.skyboxes.items():
        if skybox.shadows and shadow_id in skybox.shadows:
            skybox.shadows.remove(shadow_id)
            del skybox.files_size['shadows'][shadow_id]
            footage.meta['skyboxes'][skybox_id] = skybox.api_repr()

    # Стираем тень
    if not request.args.get('keep_definition'):
        # meta.shadows.pop(), в принципе, нахуй не нужно — дальше редактируется сырая мета, но сырое редактирование должно уехать в meta.save_shadows()
        meta.shadows.pop(shadow_id, None)
        footage.meta['shadows'].pop(shadow_id, None)
        if not footage.meta['shadows']:
            footage.meta.pop('shadows', None)

    # Удаляем панорамы
    shutil.rmtree(footage.in_files('shadows', shadow_id), ignore_errors=True)

    flag_modified(footage, 'meta')
    db.session.commit()

    return '', 204


@mod.route('/tours/<int:tour_id>/multimenu_price/invoice/send', methods=('POST', ))
def multimenu_price_invoice(tour_id):
    """
    Input:
    {
        "email": str,
        "choices": {multichoice_key: item_id, ...}
    }
    :param tour_id:
    :return:
    """
    tour = load_tour_view(tour_id)

    choices = request.json.get('choices')
    if not choices:
        abort(400, gettext('Bad request: nothing selected.'))

    # Проверяем тур (в нём должно быть мультименю и shadows_multimenu_price.invoice.disabled == False
    multimenu = tour.footage.meta.get('shadows_multimenu')
    invoice_config = tour.footage.meta.get('shadows_multimenu_price', {}).get('invoice', {})
    if not multimenu or invoice_config.get('disabled', False):
        abort(400, 'This tour does not support invoice generation.')

    # Проверяем ema
    email = request.json.get('email')
    if not email:
        abort(400, gettext('The email address is not valid.'))
    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.email
    except EmailNotValidError as e:
        abort(400, gettext('The email address is not valid.'))

    # Составляем список предметов
    table = []
    total_price = 0
    for menu in multimenu:
        if menu['multichoice_key'] not in choices:
            continue
        for item in menu['contents']:
            if item.get('id') == choices[menu['multichoice_key']]:
                price = item.get('price')
                table.append({'category': menu.get('title'), 'title': item.get('title'), 'price': price})
                if price:
                    total_price += price
                break

    # Проверяем шаблон
    template = invoice_config.get('template')
    if template is None:
        template = '_default'
    try:
        send_email(
            gettext('You selection in tour "%(title)s"', title=tour.title), [email],
            template='front/tour/invoices/' + template,
            tour=tour, table=table, total_price=total_price
        )
    except jinja2.exceptions.TemplateNotFound:
        abort(400, gettext('Template "%(template)s" not found.', template=template))

    log = logging.getLogger('misc')
    log.info('IKEA multimenu invoice: tour_id={}, ip={}, choices={}'.format(tour.id, request.remote_addr, choices))

    return '', 204
