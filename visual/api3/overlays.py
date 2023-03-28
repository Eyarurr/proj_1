from flask import request, abort
from flask_login import login_required
from flask_babel import gettext

from visual.models.meta import TourMetaInside, Overlay
from . import mod, api_response
from .common import load_tour_edit, load_tour_view


@mod.route('/tours/<int:tour_id>/virtual/overlays')
def get_overlays(tour_id):
    tour = load_tour_view(tour_id)
    meta = TourMetaInside(tour)

    result = {}
    for overlay_id, overlay in meta.overlays.items():
        result[overlay_id] = overlay.api_repr()

    return api_response(result)


@mod.route('/tours/<int:tour_id>/virtual/overlays/<overlay_id>')
def get_overlay(tour_id, overlay_id):
    tour = load_tour_view(tour_id)
    meta = TourMetaInside(tour)

    if overlay_id not in meta.overlays:
        abort(404, gettext('Overlay %(overlay_id)s not found.', overlay_id=overlay_id))

    return api_response(meta.overlays[overlay_id].api_repr())


@login_required
@mod.route('/tours/<int:tour_id>/virtual/overlays', methods=('POST', ))
def post_overlays(tour_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    overlay_id = meta.next_overlay_id()
    meta.overlays[overlay_id] = Overlay(id=overlay_id, meta=meta)
    warnings = meta.overlays[overlay_id].update_from_api_request(request.json)
    meta.save_overlays(to_db=True)

    return api_response(tour.meta.get('overlays', {}), warnings=warnings)


@login_required
@mod.route('/tours/<int:tour_id>/virtual/overlays/<overlay_id>', methods=('PUT', ))
def put_overlay(tour_id, overlay_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    if overlay_id not in meta.overlays:
        meta.overlays[overlay_id] = Overlay(id=overlay_id, meta=meta)
    warnings = meta.overlays[overlay_id].update_from_api_request(request.json)
    meta.save_overlays(to_db=True)

    return api_response(meta.overlays[overlay_id].api_repr(), warnings=warnings)


@login_required
@mod.route('/tours/<int:tour_id>/virtual/overlays', methods=('PUT', ))
def put_overlays(tour_id):
    warnings = []
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    for overlay_id, overlay_data in request.json.items():
        if overlay_id not in meta.overlays:
            meta.overlays[overlay_id] = Overlay(id=overlay_id, meta=meta)
        warnings += meta.overlays[overlay_id].update_from_api_request(overlay_data)
    meta.save_overlays(to_db=True)

    return api_response({k: v.api_repr() for k, v in meta.overlays.items()}, warnings=warnings)


@login_required
@mod.route('/tours/<int:tour_id>/virtual/overlays/<overlay_id>', methods=('DELETE', ))
def delete_overlay(tour_id, overlay_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    if overlay_id not in meta.overlays:
        abort(404, gettext('Overlay %(overlay_id)s not found.', overlay_id=overlay_id))
    del meta.overlays[overlay_id]
    meta.save_overlays(to_db=True)

    return '', 204

