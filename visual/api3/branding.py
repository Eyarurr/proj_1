"""
API брендинга туров.
"""

import os
import shutil

from PIL import Image
from flask import request, abort
from flask_login import login_required
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified

from . import mod, api_response
from visual.models.meta import TourMetaInside, Branding
from ..core import db
from visual.util import downsize_img, unlink_calm, get_flow_file
from .common import load_tour_edit, handle_asset_param


def _get_size(val):
    """Проверяет тип свойства тела запроса с размером и возвращает его в виде списека [int, int]"""
    try:
        size = (int(val[0]), int(val[1]))
    except (KeyError, ValueError, IndexError):
        abort(400, gettext('Bad data type for property %(property)s', property='big@resize'))
    return size


def validate_watermark(payload):
    """Валидирует watermark"""
    positions = ('top-left', 'top-center', 'top-right', 'left', 'center', 'right', 'bottom-left', 'bottom-center', 'bottom-right')

    if not isinstance(payload, dict):
        abort(400, gettext('Invalid %(property)s value', property='\"watermark\"'))

    if payload.get('position', None):
        if payload['position'] not in positions:
            abort(400, gettext('Invalid %(property)s value', property='\"position\"'))

    if payload.get('opacity', None):
        if not 0 <= float(payload['opacity']) <= 1:
            abort(400, gettext('Invalid %(property)s value', property='\"opacity\"'))


def update_branding_from_api_request(branding, payload):
    """Обновляет Branding из payload апишного запроса.
    """
    warnings = []
    simple_props = {'copyright_map': str, 'copyright_help': str, 'logo_help_link': str}
    skip_props = {'logo_help@resize', 'logo_help_disabled'}
    for key, value in payload.items():
        if key in simple_props:
            if value is None:
                setattr(branding, key, None)
            else:
                try:
                    setattr(branding, key, simple_props[key](value))
                except TypeError:
                    abort(400, gettext('Bad data type for property %(property)s', property=key))

        elif key == 'watermark':
            if not branding.watermark:
                branding.watermark = {}

            if value is None or 'url' in value:
                if branding.watermark and branding.watermark['url']:
                    unlink_calm(branding.meta.tour.in_files(branding.watermark['url']))

            if value:
                validate_watermark(value)

                if value.get('url', None):
                    branding.meta.tour.mkdir()
                    os.makedirs(branding.meta.tour.in_files('branding'), exist_ok=True)
                    try:
                        with handle_asset_param(value['url'], 'url') as (fh, *_):
                            file = fh.read()
                            img = Image.open(fh)
                            dst_filename = branding.gen_filename(img.format.lower())
                            dst = branding.meta.tour.in_files('branding', dst_filename)
                            with open(dst, 'wb') as out:
                                out.write(file)
                    except ValueError as e:
                        abort(400, str(e))
                    value['url'] = 'branding/' + dst_filename

                branding.watermark.update(value)
                branding.watermark = {key: val for key, val in branding.watermark.items() if val is not None}
            else:
                branding.watermark = None

        elif key == 'logo_help':
            if branding.logo_help:
                unlink_calm(branding.meta.tour.in_files(branding.logo_help))
            if value:
                branding.meta.tour.mkdir()
                os.makedirs(branding.meta.tour.in_files('branding'), exist_ok=True)

                try:
                    with handle_asset_param(value, 'logo_help') as (fh, *_):
                        file = fh.read()
                        img = Image.open(fh)
                        dst_filename = branding.gen_filename(img.format.lower())
                        img.close()
                        dst = branding.meta.tour.in_files('branding', dst_filename)
                        with open(dst, 'wb') as out:
                            out.write(file)
                except ValueError as e:
                    abort(400, str(e))

                branding.logo_help = 'branding/' + dst_filename
            else:
                branding.logo_help = ''

        elif key == 'logo_help@flow':
            if branding.logo_help:
                unlink_calm(branding.meta.tour.in_files(branding.logo_help))

            if value is None:
                branding.logo_help = None
            else:
                src, _, _ = get_flow_file(payload, 'logo_help@flow')
                filename, ext = os.path.splitext(src)

                branding.meta.tour.mkdir()
                os.makedirs(branding.meta.tour.in_files('branding'), exist_ok=True)
                dst_filename = branding.gen_filename(ext)
                dst = branding.meta.tour.in_files('branding', dst_filename)

                if 'logo_help@resize' in payload:
                    downsize_img(src, dst, _get_size(payload['logo_help@resize']), 'fit', True)
                else:
                    shutil.copy(src, dst)

                branding.logo_help = 'branding/' + dst_filename
        elif key == 'logo_help_disabled':
            if branding.logo_help:
                unlink_calm(branding.meta.tour.in_files(branding.logo_help))

            branding.logo_help = ''

        elif key not in skip_props:
            warnings.append(gettext('Unknown input property %(property)s', property=key))

    return warnings


@mod.route('/tours/<int:tour_id>/branding', methods=('PUT', ))
@login_required
def put_tour_branding(tour_id):
    """
    PUT /tours/<tour_id>/branding
    Input:
        {
            "copyright_map": str,
            "copyright_help": str,
            "logo_help@flow": "token/filename"
            "logo_help@resize": [w, h],
            "logo_help_disabled": bool
            "logo_help_link": str
            "watermark": dict
                        {
                        url: url,
                        position: "bottom-right",  // значения: "top-left", "top-center", "top-right", "left", "center", "right", "bottom-left", "bottom-center", "bottom-right", default="bottom-right"
                        opacity: 0.3,  // default=0.5 }
        }
    Output:
        Branding
    """
    tour = load_tour_edit(tour_id)
    if 'branding' not in tour.paid_features_time_left():
        abort(403, gettext('There is no "branding" feature purchased for this tour.'))

    meta = TourMetaInside(tour)

    if not meta.branding:
        meta.branding = Branding(meta, {})

    warnings = update_branding_from_api_request(meta.branding, request.json)

    tour.meta.setdefault('branding')
    tour.meta['branding'] = meta.branding.api_repr()
    flag_modified(tour, 'meta')
    db.session.commit()

    return api_response(tour.meta['branding'], warnings=warnings)
