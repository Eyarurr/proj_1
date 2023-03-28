import hashlib
import os
import shutil
import uuid

from flask import request, abort, current_app
from flask_login import login_required
from flask_babel import gettext

from visual.models.meta import TourMetaInside, Action
from . import mod, api_response
from .common import load_tour_edit, load_tour_view
from ..util import get_flow_file, unlink_calm
from PIL import Image, UnidentifiedImageError


@mod.route('/tours/<int:tour_id>/actions')
def get_actions(tour_id):
    tour = load_tour_view(tour_id)
    meta = TourMetaInside(tour)

    result = {}
    for action_id, action in meta.actions.items():
        result[action_id] = action.api_repr()

    return api_response(result)


@mod.route('/tours/<int:tour_id>/actions/<action_id>')
def get_action(tour_id, action_id):
    tour = load_tour_view(tour_id)
    meta = TourMetaInside(tour)

    if action_id not in meta.actions:
        abort(404, gettext('Action "%(action_id)s" not found.', action_id=action_id))

    return api_response(meta.actions[action_id].api_repr())


@login_required
@mod.route('/tours/<int:tour_id>/actions', methods=('POST', ))
def post_actions(tour_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    action_id = meta.next_action_id()
    if 'type' not in request.json or request.json['type'] not in Action.TYPES:
        abort(400, gettext('Unknown action type.'))
    # @todo: Проверки на необходимые поля при создании объекта могут быть здесь, тогда можно в PUT-запросах не указывать их

    meta.actions[action_id] = Action.create(type_=request.json['type'])
    warnings = meta.actions[action_id].update_from_api_request(request.json, meta)
    meta.save_actions(to_db=True)

    return api_response(tour.meta.get('actions', {}), warnings=warnings)


@login_required
@mod.route('/tours/<int:tour_id>/actions/<action_id>', methods=('PUT', ))
def put_action(tour_id, action_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    if action_id not in meta.actions:
        if 'type' not in request.json or request.json['type'] not in Action.TYPES:
            abort(400, gettext('Unknown action type.'))
        meta.actions[action_id] = Action.create(type_=request.json['type'])
    else:
        if request.json['type'] != meta.actions[action_id].type:
            abort(400, gettext('You can not change action type.'))
    warnings = meta.actions[action_id].update_from_api_request(request.json, meta)
    meta.save_actions(to_db=True)

    return api_response(meta.actions[action_id].api_repr(), warnings=warnings)


@login_required
@mod.route('/tours/<int:tour_id>/actions/<action_id>', methods=('DELETE', ))
def delete_action(tour_id, action_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    if action_id not in meta.actions:
        abort(404, gettext('Action "%(action_id)s" not found.', action_id=action_id))
    if getattr(meta.actions[action_id], 'image', None):
        unlink_calm(tour.in_files(meta.actions[action_id].image))
    del meta.actions[action_id]
    meta.save_actions(to_db=True)

    return '', 204


@login_required
@mod.route('/tours/<int:tour_id>/actions', methods=('DELETE', ))
def delete_actions(tour_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)
    for key in  meta.actions.keys():
        if getattr(meta.actions[key], 'image', None):
          unlink_calm(tour.in_files(meta.actions[key].image))
    meta.actions = {}
    meta.save_actions(to_db=True)

    return '', 204
