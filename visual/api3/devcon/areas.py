from flask import request, abort, current_app, url_for
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCProject, DCArea, DCMembership, DCTour, DCDrawing, User, TourSeen, DCTask, DCTaskSeen
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query
from . import create_projects_query


@mod.route('/devcon/projects/<int:project_id>/areas', methods=('POST', ))
@login_required
def post_devcon_areas(project_id):
    """
    POST /devcon/projects/<id>/members
    Input:
    {
        parent_id: int|null,
        title: str,
    }
    """
    try:
        title = request.json.get('title', '').strip()
        assert title
        assert type(title) is str
    except:
        abort(400, gettext('The area title is not valid.'))
        return

    project, membership, *_ = create_projects_query().filter(DCProject.id == project_id).first_or_404(description=gettext('Project not found.'))

    if 'admin' not in membership.roles and 'super' not in membership.roles:
        abort(403, gettext('You can not create areas in this project.'))

    parent_id = request.json.get('parent_id')
    if parent_id is not None:
        DCArea.query.filter_by(project_id=project.id, id=parent_id).first_or_404(description=gettext('Parent area not found.'))

    if 'sort' in request.json:
        try:
            sort = int(request.json['sort'])
        except:
            abort(400, gettext('Area sorting order is not valid.'))
            return
    else:
        sort = db.session.query(db.func.max(DCArea.sort)).filter(DCArea.project_id == project.id, DCArea.parent_id == parent_id).scalar() or 0
        sort += 1

    area = DCArea(project_id=project.id, created_by=current_user.id, parent_id=parent_id, sort=sort, title=title)
    db.session.add(area)
    db.session.commit()

    return api_response(area.api_repr())


@mod.route('/devcon/projects/<int:project_id>/areas', methods=('GET', ))
@login_required
def get_devcon_areas(project_id):
    """
    GET /devcon/projects/<id>/members
    Output:
    [DCArea, ...]
    """
    project, membership, *_ = create_projects_query().filter(DCProject.id == project_id).first_or_404(description=gettext('Project not found.'))

    q = db.session.query(DCArea, db.func.count(TourSeen.seen), db.func.count(DCTaskSeen.time_task))\
        .filter(DCArea.project_id == project.id)\
        .outerjoin(DCTask, DCTask.area_id == DCArea.id) \
        .outerjoin(DCTaskSeen, db.and_(DCTaskSeen.task_id == DCTask.id, DCTaskSeen.user_id == current_user.id))\
        .outerjoin(DCTour) \
        .outerjoin(TourSeen, db.and_(TourSeen.tour_id == DCTour.tour_id, TourSeen.user_id == current_user.id)) \
        .group_by(DCArea.id, db.text('users_1.id'))\
        .options(db.joinedload(DCArea.creator))

    result = []
    for area, cnt_tours_seen, cnt_tasks_seen in q.all():
        result.append(area.api_repr(cnt_tours_seen=cnt_tours_seen, cnt_tasks_seen=cnt_tasks_seen))

    return api_response(result)


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>', methods=('GET', ))
@login_required
def get_devcon_area(project_id, area_id):
    """
    GET /devcon/projects/<id>/members
    Output:
    [DCArea, ...]
    """
    project, membership, *_ = create_projects_query().filter(DCProject.id == project_id).first_or_404(description=gettext('Project not found.'))

    area, cnt_tasks_seen = db.session.query(DCArea, db.func.count(DCTaskSeen.time_task)) \
        .outerjoin(DCTask, DCTask.area_id == DCArea.id) \
        .outerjoin(DCTaskSeen, db.and_(DCTaskSeen.task_id == DCTask.id, DCTaskSeen.user_id == current_user.id))\
        .filter(DCArea.project_id == project.id, DCArea.id == area_id)\
        .group_by(DCArea.id, db.text('users_1.id'))\
        .options(db.joinedload(DCArea.creator))\
        .first_or_404(description='Area not found.')

    return api_response(area.api_repr(cnt_tasks_seen=cnt_tasks_seen))


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>', methods=('PUT', ))
@login_required
def put_devcon_area(project_id, area_id):
    """
    PUT /devcon/projects/<id>/members
    {title, parent_id}
    Output:
    [DCArea, ...]
    """
    project, membership, *_ = create_projects_query().filter(DCProject.id == project_id).first_or_404(description=gettext('Project not found.'))

    if 'admin' not in membership.roles and 'super' not in membership.roles:
        abort(403, gettext('You can not create areas in this project.'))

    area = DCArea.query.filter_by(project_id=project.id, id=area_id).options(db.joinedload(DCArea.creator)).first_or_404(description='Area not found.')

    if 'title' in request.json:
        try:
            title = request.json['title'].strip()
            assert title
            assert type(title) is str
        except:
            abort(400, gettext('The area title is not valid.'))
            return
        area.title = title

    if 'parent_id' in request.json:
        if request.json['parent_id'] is None:
            parent_id = None
        else:
            try:
                parent_id = int(request.json['parent_id'])
            except:
                abort(400, gettext('Wrong parent area.'))
                return

        if parent_id != area.parent_id:
            if parent_id is not None:
                parent = DCArea.query.filter_by(project_id=area.project_id, id=parent_id) \
                    .first_or_404(description=gettext('Parent area not found.'))

                # Проверяем, что нового родителя нет среди потомков
                for child in area.descendants().all():
                    if child.id == parent.id:
                        abort(400, gettext('Attaching area to its child area is not allowed.'))

            area.parent_id = parent_id

    if 'sort' in request.json:
        try:
            area.sort = int(request.json['sort'])
        except:
            abort(400, gettext('Area sorting order is not valid.'))

    db.session.commit()

    return api_response(area.api_repr())


@mod.route('/devcon/projects/<int:project_id>/areas/<int:area_id>', methods=('DELETE', ))
@login_required
def delete_devcon_area(project_id, area_id):
    """
    DELETE /devcon/projects/<id>/members
    """
    project, membership, *_ = create_projects_query().filter(DCProject.id == project_id).first_or_404(description=gettext('Project not found.'))

    if 'admin' not in membership.roles and 'super' not in membership.roles:
        abort(403, gettext('You can not create areas in this project.'))

    area = DCArea.query.filter_by(project_id=project.id, id=area_id).options(db.joinedload(DCArea.creator)).first_or_404(description='Area not found.')

    # Вот дохуя интересный вопрос, почему db.session.delete(area) не выполняет каскадное удаление потомков, но разбираться некогда
    # db.session.delete(area)
    db.session.execute(f'DELETE FROM dc_areas WHERE id = {area.id}')
    db.session.commit()

    return '', 204
