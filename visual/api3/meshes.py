from flask import request, abort
from flask_login import login_required
from flask_babel import gettext

from visual.models.meta import TourMetaInside, ActiveMesh
from . import mod, api_response
from .common import load_tour_edit, load_tour_view


@login_required
@mod.route('/tours/<int:tour_id>/active_meshes/<mesh_id>', methods=('PUT',))
def put_active_meshes(tour_id, mesh_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)
    if mesh_id not in meta.active_meshes:
        meta.active_meshes[mesh_id] = ActiveMesh(id=mesh_id, meta=meta)
    warnings = meta.active_meshes[mesh_id].update_from_api_request(request.json)
    meta.save_active_mesh(to_db=True)
    return api_response({k: v.api_repr() for k, v in meta.active_meshes.items()}, warnings=warnings)


@login_required
@mod.route('/tours/<int:tour_id>/active_meshes/<mesh_id>', methods=('DELETE',))
def delete_active_meshes(tour_id, mesh_id):
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)
    if mesh_id not in meta.active_meshes:
        abort(404, gettext('ActiveMesh %(active_meshes)s not found.', active_meshes=mesh_id))
    del meta.active_meshes[mesh_id]
    meta.save_active_mesh(to_db=True)
    return '', 204


@mod.route('/tours/<int:tour_id>/active_meshes/<mesh_id>')
def get_active_meshes(tour_id, mesh_id):
    tour = load_tour_view(tour_id)
    meta = TourMetaInside(tour)
    return api_response(meta.active_meshes[mesh_id].api_repr())
