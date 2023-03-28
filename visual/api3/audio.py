from flask import request, abort
from flask_login import current_user, login_required
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.models import Tour
from visual.models.meta import TourMetaInside, AudioClip
from visual.util import unlink_calm, get_flow_file
from . import mod, api_response
from .common import load_tour_edit


def update_audioclip_from_api_request(audioclip, payload):
    """Обновляет AudioClip из апишного запроса."""
    warnings = []
    simple_props = {'title': str, 'volume': float, 'pause': float, 'loop': bool}
    skip_props = {}

    for key, value in payload.items():
        if key in simple_props:
            if value is None:
                setattr(audioclip, key, None)
            else:
                try:
                    setattr(audioclip, key, simple_props[key](value))
                except TypeError:
                    abort(400, gettext('Bad data type for property %(property)s', property=key))
        elif key == 'url@flow':
            src, _, _ = get_flow_file(payload, 'url@flow')
            audioclip.set_mp3(src)
        elif key not in skip_props:
            warnings.append(gettext('Unknown input property %(property)s', property=key))

    return warnings


def clean_tour_audio(tour):
    # Удаляем все TourSkybox.audio
    for skybox_id, skybox in tour.meta.get('skyboxes', {}).items():
        skybox.pop('audio', None)

    # Удаляем файлы озвучки
    for clip_id, clip in tour.meta.get('audio', {}).items():
        unlink_calm(tour.in_files(clip['url']))

    tour.meta.pop('audio', None)


@mod.route('/tours/<int:tour_id>/audio/<clip_id>', methods=('PUT', ))
@login_required
def put_tour_audio_clip(tour_id, clip_id):
    """PUT /tours/<tour_id>/audio
    Изменить один клип в фонотеке.
    """
    tour = load_tour_edit(tour_id, required_types=('real', 'virtual'), required_statuses=('testing', 'published'))
    meta = TourMetaInside(tour)

    if clip_id not in meta.audio:
        if not request.json.get('url@flow'):
            abort(404, gettext("URL must be specified for action \"sound\"."))
        meta.audio[clip_id] = AudioClip(meta, clip_id, {})

    warnings = update_audioclip_from_api_request(meta.audio[clip_id], request.json)

    tour.meta.setdefault('audio', {})
    tour.meta['audio'][clip_id] = meta.audio[clip_id].api_repr()
    flag_modified(tour, 'meta')
    tour.save_features()
    db.session.commit()

    return api_response(tour.meta['audio'][clip_id], warnings=warnings)


@mod.route('/tours/<int:tour_id>/audio', methods=('PUT', ))
@login_required
def put_tour_audio(tour_id):
    """PUT /tours/<tour_id>/audio
    Изменить несколько клипов в фонотеке.
    """
    tour = load_tour_edit(tour_id, required_types=('real', 'virtual'), required_statuses=('testing', 'published'))
    meta = TourMetaInside(tour)

    audio = tour.meta.setdefault('audio', {})
    warnings = []

    for clip_id, clip_request in request.json.items():
        if clip_id not in meta.audio:
            if not clip_request.get('url@flow'):
                abort(404, gettext("URL must be specified for action \"sound\"."))
            meta.audio[clip_id] = AudioClip(meta, clip_id, {})
        warnings += update_audioclip_from_api_request(meta.audio[clip_id], clip_request)
        audio[clip_id] = meta.audio[clip_id].api_repr()

    tour.meta['audio'] = audio
    flag_modified(tour, 'meta')
    tour.save_features()
    db.session.commit()

    return api_response(audio, warnings=warnings)


@mod.route('/tours/<int:tour_id>/audio', methods=('DELETE', ))
@login_required
def delete_tour_audio(tour_id):
    """DELETE /tours/<tour_id>/audio
    Удаляет всю фонотеку и упоминания треков.
    """
    tour = load_tour_edit(tour_id, required_types=('real', 'virtual'), required_statuses=('testing', 'published'))

    if 'audio' not in tour.meta:
        abort(400, gettext('There are no audio tracks in tour.'))

    clean_tour_audio(tour)

    flag_modified(tour, 'meta')
    tour.save_features()
    db.session.commit()

    return '', 204


@mod.route('/tours/<int:tour_id>/audio/<clip_id>', methods=('DELETE', ))
@login_required
def delete_tour_audio_clip(tour_id, clip_id):
    """DELETE /tours/<tour_id>/audio/<clip_id>
    Удаляет клип из фонотеки и все упоминания о нём.
    """
    tour = load_tour_edit(tour_id, required_types=('real', 'virtual'), required_statuses=('testing', 'published'))

    if 'audio' not in tour.meta:
        abort(400, gettext('There are no audio tracks in tour.'))

    if clip_id not in tour.meta['audio']:
        abort(400, gettext('Track %(clip_id)s not found.', clip_id=clip_id))

    for skybox_id, skybox in tour.meta.get('skyboxes', {}).items():
        if 'audio' not in skybox:
            continue
        skybox['audio'].pop(clip_id, None)
        if not skybox['audio']:
            skybox.pop('audio', None)

    unlink_calm(tour.in_files(tour.meta['audio'][clip_id]['url']))
    tour.meta['audio'].pop(clip_id, None)
    if not tour.meta['audio']:
        tour.meta.pop('audio', None)

    flag_modified(tour, 'meta')
    tour.save_features()
    db.session.commit()

    return api_response(tour.meta.get('audio'))
