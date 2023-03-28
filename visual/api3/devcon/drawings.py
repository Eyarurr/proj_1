from flask import request, abort, current_app, url_for
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCProject, DCArea, DCMembership, DCDrawing
from visual.api3 import mod, api_response
from visual.api3.common import handle_asset_param
from . import create_projects_query


def load_project_membership_area(project_id, area_id) -> (DCProject, DCMembership, DCArea):
    q = create_projects_query()\
        .add_columns(DCArea)\
        .join(DCArea)\
        .filter(DCProject.id == project_id, DCArea.id == area_id)
    project, membership, *_, area = q.first_or_404(description=gettext('Project or area not found.'))

    return project, membership, area


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/drawings', methods=('POST', ))
@login_required
def post_devcon_drawings(project_id, area_id):
    """
    POST /devcon/projects/<id>/areas/<id>/drawings
    Input:
    {
        title: str,
        file: asset
    }
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    if 'admin' not in membership.roles and 'super' not in membership.roles and 'plotman' not in membership.roles:
        abort(403, gettext('You can not add drawings in this project.'))

    try:
        title = request.json['title'].strip()
        assert title
    except:
        abort(400, gettext('Invalid drawing title.'))
        return

    if 'file' not in request.json:
        abort(400, gettext('Drawing file is not uploaded.'))

    drawing = DCDrawing(
        created_by=current_user.id, creator=current_user,
        area_id=area.id, area=area,
        title=title
    )
    db.session.add(drawing)
    db.session.flush()
    with handle_asset_param(request.json['file'], 'file') as (fh, *_):
        drawing.file = fh
    area.cnt_drawings += 1
    db.session.commit()

    return api_response(drawing.api_repr())


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/drawings', methods=('GET', ))
@login_required
def get_devcon_drawings(project_id, area_id):
    """
    GET /devcon/projects/<id>/areas/<id>/drawings
    Query String:
        ?children=1 - с турами у областей-детей
    Output:
    [DCDrawing, ...]
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    q = DCDrawing.query

    if request.args.get('children') == '1':
        children = area.descendants(with_self=True).all()
        # @todo: потенциальное место для оптимизации: проджойнить с рекурсивным запросом на получение детей области?
        q = q.filter(DCDrawing.area_id.in_([x.id for x in children]))
    else:
        q = q.filter(DCDrawing.area_id == area.id)

    q = q.order_by(DCDrawing.created.desc())

    result = []
    for drawing in q.all():
        result.append(drawing.api_repr())

    return api_response(result)


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/drawings/<int:drawing_id>', methods=('PUT', ))
@login_required
def put_devcon_drawing(project_id, area_id, drawing_id):
    """
    PUT /devcon/projects/<id>/areas/<id>/drawings/<id>
    Input:
    {area_id: int}
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    if 'admin' not in membership.roles and 'super' not in membership.roles and 'plotman' not in membership.roles:
        abort(403, gettext('You can not change drawings in this project.'))

    drawing = DCDrawing.query.filter_by(area_id=area.id, id=drawing_id).first_or_404(gettext('Drawing not found in this area.'))

    if 'area_id' in request.json:
        new_area = DCArea.query.filter_by(project_id=project.id, id=request.json.get('area_id')).first_or_404(gettext('Target area not found.'))
        drawing.area_id = new_area.id
        area.cnt_drawings -= 1
        new_area.cnt_drawings += 1

    if 'title' in request.json:
        try:
            drawing.title = request.json['title'].strip()
            assert drawing.title
        except:
            abort(400, gettext('Please enter drawing title.'))
            return

    if 'file' in request.json:
        with handle_asset_param(request.json['file'], 'file') as (fh, *_):
            drawing.file = fh

    db.session.commit()

    return api_response(drawing.api_repr())


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>/drawings/<int:drawing_id>', methods=('DELETE', ))
@login_required
def delete_devcon_drawings(project_id, area_id, drawing_id):
    """
    DELETE /devcon/projects/<id>/areas/<id>/drawings/<id>
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    if 'admin' not in membership.roles and 'super' not in membership.roles and 'plotman' not in membership.roles:
        abort(403, gettext('You can not delete drawings in this project.'))

    drawing = DCDrawing.query.filter_by(area_id=area.id, id=drawing_id).first_or_404(gettext('Drawing not found in this area.'))
    del drawing.file
    db.session.delete(drawing)
    area.cnt_drawings -= 1
    db.session.commit()

    return '', 204
