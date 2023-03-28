import json
import time

from flask import request, abort, current_app, url_for
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCProject, DCArea, DCMembership, DCTour, DCDrawing, User
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query, handle_asset_param
from . import create_projects_query


def project_repr_with_counters(project, membership, cnt_areas, cnt_members, cnt_tours, fields):
    """
    Возвращает API-представление DCProject с учётом дополнительных полей в `fields`
    :param project: DCProject
    :param membership: DCMembership
    :param cnt_areas: int
    :param cnt_members: int
    :param cnt_tours: int
    :param fields: string
    :return:
    """
    obj = project.api_repr(membership=membership.api_repr())
    if 'cnt_areas' in fields:
        obj['cnt_areas'] = cnt_areas or 0
    if 'cnt_members' in fields:
        obj['cnt_members'] = cnt_members or 0
    if 'cnt_tours' in fields:
        obj['cnt_tours'] = cnt_tours or 0
    return obj


@mod.route('/devcon/projects', methods=('POST', ))
@login_required
def post_devcon_projects():
    """
    POST /devcon/projects
    Создаёт проект
    Ответ:
        DCProject
    """
    try:
        title = request.json['title'].strip()
        assert title
    except:
        abort(400, gettext('Malformed %(key)s value.', key='title'))

    if 'details' in request.json:
        if type(request.json['details']) is not dict:
            abort(400, gettext('Malformed %(key)s value.', key='title'))
        details = request.json['details']
    else:
        details = {}

    project = DCProject(
        user_id=current_user.id,
        title=title,
        details=details
    )
    db.session.add(project)
    db.session.flush()

    if 'icon' in request.json:
        with handle_asset_param(request.json['icon'], 'icon') as (fh, *_):
            project.icon = fh

    membership = DCMembership(user_id=current_user.id, roles=['super'])
    project.members.append(membership)
    db.session.commit()

    return api_response(project.api_repr(membership=membership.api_repr()))


@mod.route('/devcon/projects', methods=('GET', ))
@login_required
def get_devcon_projects():
    """
    GET /devcon/projects
    GET:
        ?offset
        ?limit
        ?sort: created, title, joined; "-" в начале означает обратную сортировку
        ?fields: список полей в ответе, через запятую: cnt_areas, cnt_members, cnt_tours
    """
    result = []

    fields = request.args.get('fields', '').split(',')

    q = create_projects_query(fields)

    # Сортировка
    orders = {
        'created': DCProject.created,
        'title': DCProject.title,
        'joined': DCMembership.since
    }
    q = apply_sort_to_query(q, request.args.get('sort', '-joined'), orders)

    # Лимит, оффсет
    offset = request.args.get('offset', type=int)
    if offset:
        q = q.offset(offset)
    limit = request.args.get('limit', 500, type=int)
    if limit:
        q = q.limit(limit)

    for project, membership, cnt_areas, cnt_members, cnt_tours in q.all():
        obj = project_repr_with_counters(project, membership, cnt_areas, cnt_members, cnt_tours, fields)
        result.append(obj)

    return api_response(result)


@mod.route('/devcon/projects/<int:project_id>', methods=('GET', ))
@login_required
def get_devcon_project(project_id):
    """
    GET /devcon/projects/<id>
    Параметры Query String:
        ?fields: список полей в ответе, через запятую: cnt_areas, cnt_members, cnt_tours
    """
    fields = request.args.get('fields', '').split(',')

    q = create_projects_query(fields).filter(DCProject.id == project_id)

    project, membership, cnt_areas, cnt_members, cnt_tours = q.first_or_404(description='Project not found.')
    obj = project_repr_with_counters(project, membership, cnt_areas, cnt_members, cnt_tours, fields)

    return api_response(obj)


@mod.route('/devcon/projects/<int:project_id>', methods=('PUT', ))
@login_required
def put_devcon_project(project_id):
    """
    PUT /devcon/projects/<id>
    Request body:
    {
        title, details,
        icon: 'flow@TOKEN/filename' or 'datauri@data'
    }
    """
    q = create_projects_query().filter(DCProject.id == project_id)
    project, membership, *_ = q.first_or_404(description='Project not found.')

    if 'admin' not in membership.roles and 'super' not in membership.roles:
        abort(403, gettext('You can not edit this project properties.'))

    if 'title' in request.json:
        try:
            title = request.json['title'].strip()
            assert title
        except:
            abort(400, gettext('Please enter project title.'))
            return
        project.title = title

    if 'details' in request.json:
        details = request.json['details']
        if type(details) is not dict:
            abort(400, gettext('Malformed %(key)s value.', key='details'))
        project.details = details

    if 'icon' in request.json:
        with handle_asset_param(request.json['icon'], 'icon') as (fh, *_):
            project.icon = fh

    db.session.commit()

    obj = project_repr_with_counters(project, membership, None, None, None, [])
    return api_response(obj)


@mod.route('/devcon/projects/<int:project_id>', methods=('DELETE', ))
@login_required
def delete_devcon_project(project_id):
    """
    DELETE /devcon/projects/<id>
    """
    q = create_projects_query().filter(DCProject.id == project_id)
    project, membership, *_ = q.first_or_404(description='Project not found.')

    if 'super' not in membership.roles:
        abort(403, gettext('You can not edit this project properties.'))

    db.session.delete(project)
    db.session.commit()

    return '', 204
