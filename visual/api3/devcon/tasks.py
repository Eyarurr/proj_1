import datetime
import re

from flask import request, abort
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCArea, DCTask, DCTaskSeen, DCTour, User
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query
from . import load_project_membership, load_project_membership_area, load_project_membership_area_task


@mod.post('/devcon/projects/<int:project_id>/areas/<int:area_id>/tasks')
@login_required
def post_devcon_tasks(project_id, area_id):
    """
    POST /devcon/projects/<id>/areas/<id>/tasks
    """
    project, membership, area = load_project_membership_area(project_id, area_id)

    if not membership.has_role('admin', 'taskman'):
        abort(403, gettext('You can not create tasks in this project.'))

    if 'status' not in request.json:
        abort(400, gettext('You must select task status.'))
    if request.json['status'] not in ('draft', 'todo'):
        abort(400, gettext('You can not create new task with "%(status)s" status.', status=request.json['status']))
    if 'title' not in request.json:
        abort(400, gettext('You should at least enter task title.'))

    task = DCTask(
        area=area,
        area_id=area.id,
        created_by=current_user.id
    )
    task.update_from_api_request(request.json)
    area.cnt_tasks += 1

    tour_id = request.json.get('tour_id')
    if tour_id:
        dc_tour = DCTour.query.filter_by(tour_id=tour_id, area_id=area.id).first()
        dc_tour.cnt_tasks += 1

    db.session.add(task)
    db.session.flush()
    task.add_comment('task.created', None)
    db.session.commit()

    return api_response(task.api_repr())


@mod.put('/devcon/projects/<int:project_id>/tasks/<task_id>')
@mod.put('/devcon/projects/<int:project_id>/areas/<int:area_id>/tasks/<task_id>')
@login_required
def put_devcon_task(project_id, task_id, area_id=None):
    """
    PUT /devcon/projects/<id>/tasks/<id>
    PUT /devcon/projects/<id>/areas/<id>/tasks/<id>
    Body:
    {area_id, assignee.id, status, title, description, priority, deadline}
    """
    def access(membership, payload, task):
        if membership.has_role('admin', 'taskman') or task.created_by == current_user.id:
            return True

        # ... до сюда долетят только не-админы и не владельцы задачи
        # им можно только менять статус в ограниченных пределах и назначать себя исполнителем ничьей задачи

        if set(request.json.keys()) - {'status', 'assignee'}:
            return False

        if 'status' in payload:
            if payload['status'] in ('progress', 'review', 'pause') and task.assigned_to == current_user.id:
                return True

        if 'assignee' in payload:
            # Назначить исполнителя не-админы могут только для задач с пустым исполнителем и только себя
            if payload['assignee'] is not None and payload['assignee'].get('id') == current_user.id \
                    and (task.assigned_to is None or task.assigned_to == current_user.id):
                return True

        return False

    project, membership, area, task = load_project_membership_area_task(project_id, area_id, task_id)

    if not access(membership, request.json, task):
        abort(403, gettext('Access Denied'))

    tour_id = task.tour_id
    changed = task.update_from_api_request(request.json)
    task.updated = datetime.datetime.now()

    if 'area_id' in request.json and request.json['area_id'] != task.area_id:
        new_area = DCArea.query\
            .filter_by(id=request.json['area_id'], project_id=project.id)\
            .first_or_404(description=gettext('Target area not found.'))
        changed['area_id'] = {'was': task.area_id, 'now': new_area.id}
        task.area_id = new_area.id
        area.cnt_tasks -= 1
        new_area.cnt_tasks += 1

    if tour_id and 'tour_id' in request.json and request.json['tour_id'] != tour_id:
        dc_tour = DCTour.query.filter_by(tour_id=tour_id, area_id=area.id).first()
        dc_tour.cnt_tasks -= 1
        if request.json['tour_id']:
            new_dc_tour = DCTour.query.filter_by(tour_id=request.json['tour_id'], area_id=area.id).first()
            new_dc_tour.cnt_tasks += 1

    if not tour_id and 'tour_id' in request.json and request.json['tour_id']:
        dc_tour = DCTour.query.filter_by(tour_id=request.json['tour_id'], area_id=area.id).first()
        dc_tour.cnt_tasks += 1

    if changed:
        task.add_comment('task.changed', changed)

    db.session.commit()

    # Загружаем seen-инфу про эту задачу
    seen = DCTaskSeen.query.filter_by(task_id=task.id, user_id=current_user.id).first()

    return api_response(task.api_repr(**DCTask.seen_props(seen)))


@mod.get('/devcon/projects/<int:project_id>/tasks/<task_id>')
@mod.get('/devcon/projects/<int:project_id>/areas/<int:area_id>/tasks/<task_id>')
@login_required
def get_devcon_task(project_id, task_id, area_id=None):
    """
    GET /devcon/projects/<id>/areas/<id>/tasks/<id>
    """
    if area_id:
        project, membership, area = load_project_membership_area(project_id, area_id)
    else:
        project, membership = load_project_membership(project_id)
        area = None

    q = db.session.query(DCTask, DCTaskSeen) \
        .outerjoin(DCTaskSeen, db.and_(DCTaskSeen.task_id == DCTask.id, DCTaskSeen.user_id == current_user.id))\
        .filter(DCTask.id == task_id)

    if area:
        q = q.filter(DCTask.area_id == area.id)

    task, seen = q.first_or_404(description=gettext('Task not found.'))

    if task.status == 'draft' and task.created_by != current_user.id:
        abort(404, gettext('Task not found.'))

    result = task.api_repr(**DCTask.seen_props(seen))

    return api_response(result)


@mod.get('/devcon/projects/<int:project_id>/tasks')
@mod.get('/devcon/projects/<int:project_id>/areas/<int:area_id>/tasks')
@login_required
def get_devcon_tasks(project_id, area_id=None):
    """
    GET /devcon/projects/<id>/areas/<id>/tasks/<id>
    """
    if area_id:
        project, membership, area = load_project_membership_area(project_id, area_id)
    else:
        project, membership = load_project_membership(project_id)
        area = None

    creator = db.aliased(User)
    assignee = db.aliased(User)
    q = db.session.query(DCTask, DCTaskSeen)\
        .join(creator, creator.id == DCTask.created_by)\
        .outerjoin(assignee, assignee.id == DCTask.assigned_to) \
        .outerjoin(DCTaskSeen, db.and_(DCTaskSeen.task_id == DCTask.id, DCTaskSeen.user_id == current_user.id))\
        .options(db.contains_eager(DCTask.creator, alias=creator))\
        .options(db.contains_eager(DCTask.assignee, alias=assignee))

    # Дети
    if area:
        if request.args.get('children') == '1':
            children = area.descendants(with_self=True).all()
            q = q.filter(DCTask.area_id.in_([x.id for x in children]))
        else:
            q = q.filter(DCTask.area_id == area.id)

    # Сортировка
    orders = {
        'created': DCTask.created,
        'updated': DCTask.updated,
        'title': DCTask.title,
        'priority': DCTask.priority,
        'deadline': DCTask.deadline,
        'status': DCTask.status,
        'creator': creator.name,
        'assignee': assignee.name,
    }
    q = apply_sort_to_query(q, request.args.get('sort', '-created'), orders)

    # Задачи со статусом 'draft' вижу только свои
    q = q.filter(db.or_(DCTask.created_by == current_user.id, DCTask.status != 'draft'))

    # Фильтры
    if 'created_by' in request.args:
        q = q.filter(DCTask.created_by == request.args['created_by'])

    if 'assigned_to' in request.args:
        q = q.filter(DCTask.assigned_to == request.args['assigned_to'])

    if 'status' in request.args:
        statuses = request.args['status'].split(',')
        q = q.filter(DCTask.status.in_(statuses))

    if 'priority' in request.args:
        if request.args['priority'][0] == '<':
            q = q.filter(DCTask.priority <= int(request.args['priority'][1:]))
        else:
            q = q.filter(DCTask.priority > int(request.args['priority']))

    if 'deadline' in request.args:
        r = re.match(r'^(>=|<=|>|<|=)(.*)$', request.args['deadline'])
        if not r:
            abort(400, 'Malformed "deadline" filter.')
        op = r.group(1)
        ts = r.group(2)
        if ts == 'today':
            dl_operators = {
                '<': db.func.date(DCTask.deadline) < db.func.current_date(),
                '<=': db.func.date(DCTask.deadline) <= db.func.current_date(),
                '=': db.func.date(DCTask.deadline) == db.func.current_date(),
                '>': db.func.date(DCTask.deadline) > db.func.current_date(),
                '>=': db.func.date(DCTask.deadline) >= db.func.current_date()
            }
        else:
            if ts == 'now':
                t = db.func.now()
            else:
                try:
                    t = datetime.datetime.fromisoformat(ts)
                except ValueError:
                    abort(400, 'Malformed datetime value in "deadline" filter')
            dl_operators = {
                '<': DCTask.deadline < t,
                '<=': DCTask.deadline <= t,
                '=': DCTask.deadline == t,
                '>': DCTask.deadline > t,
                '>=': DCTask.deadline >= t
            }
        q = q.filter(dl_operators[op])

    if 'tour_id' in request.args:
        q = q.filter(DCTask.tour_id == request.args['tour_id'])

    # Лимит, оффсет
    offset = request.args.get('offset', type=int)
    if offset:
        q = q.offset(offset)
    limit = request.args.get('limit', 50, type=int)
    if limit > 500:
        abort(400, gettext('Limit is too high.'))
    if limit:
        q = q.limit(limit)

    result = []
    for task, seen in q.all():
        result.append(task.api_repr(**DCTask.seen_props(seen)))

    return api_response(result)


@mod.delete('/devcon/projects/<int:project_id>/tasks/<task_id>')
@mod.delete('/devcon/projects/<int:project_id>/areas/<int:area_id>/tasks/<task_id>')
@login_required
def delete_devcon_task(project_id, task_id, area_id=None):
    """
    DELETE /devcon/projects/<id>/tasks/<id>
    DELETE /devcon/projects/<id>/areas/<id>/tasks/<id>
    """
    project, membership, area, task = load_project_membership_area_task(project_id, area_id, task_id)

    if not membership.has_role('admin', 'taskman') and task.created_by != current_user.id:
        abort(403, gettext('You can not delete tasks in this project.'))

    db.session.delete(task)
    area.cnt_tasks -= 1
    if task.tour_id:
        dc_tour = DCTour.query.filter_by(tour_id=task.tour_id, area_id=area.id).first()
        dc_tour.cnt_tasks -= 1

    db.session.commit()

    return '', 204


@mod.get('/devcon/projects/<int:project_id>/tasks/count')
@mod.get('/devcon/projects/<int:project_id>/areas/<int:area_id>/tasks/count')
@login_required
def get_devcon_task_count(project_id, area_id=None):
    """
    GET /devcon/projects/<id>/tasks/count
    """
    project, membership = load_project_membership(project_id)

    result = {}

    # CASE-конструкция для определения места дедлайна на временной шкале
    case = db.case(
        (DCTask.deadline.cast(db.Date) == None, 'notset'),
        (DCTask.deadline.cast(db.Date) < db.func.current_date(), 'past'),
        (DCTask.deadline.cast(db.Date) == db.func.current_date(), 'today'),
        else_='future'
    ).label('deadline_loc')

    q = db.session.query(db.func.count(), db.func.count(DCTaskSeen.time_task), DCTask.status, case)\
        .join(DCArea)\
        .outerjoin(DCTaskSeen, db.and_(DCTaskSeen.task_id == DCTask.id, DCTaskSeen.user_id == current_user.id))\
        .filter(DCArea.project_id == project.id)\
        .filter(db.or_(DCTask.created_by == current_user.id, DCTask.status != 'draft'))\
        .group_by(DCTask.status, case)

    if area_id:
        if request.args.get('children'):
            area = DCArea.query.filter_by(project_id=project.id, id=area_id).first_or_404(gettext('Area not found.'))
            children = area.descendants(with_self=True).all()
            q = q.filter(DCArea.id.in_([x.id for x in children]))
        else:
            q = q.filter(DCArea.id == area_id)

    if 'tour_id' in request.args:
        q = q.filter(DCTask.tour_id == request.args['tour_id'])

    for cnt, cnt_seen, status, deadline_loc in q.all():
        result.setdefault(status, {})
        result[status][deadline_loc] = [cnt, cnt_seen]

    return api_response(result)


@mod.post('/devcon/projects/<int:project_id>/tasks/<task_id>/seen')
@mod.post('/devcon/projects/<int:project_id>/areas/<int:area_id>/tasks/<task_id>/seen')
@login_required
def post_devcon_task_seen(project_id, task_id, area_id=None):
    """
    POST /devcon/projects/<id>/tasks/<id>/seen
    POST /devcon/projects/<id>/areas/<id>/tasks/<id>/seen
    Request body:
    {
        task: bool,        # видел ли текущий юзер описание задачи
        cnt_comments: int  # сколько он видел комментариев на тот момент
        cnt_files: int     # и сколько файлов
    }
    """
    project, membership, area, task = load_project_membership_area_task(project_id, area_id, task_id)

    seen = DCTaskSeen.query.filter_by(task_id=task.id, user_id=current_user.id).first()
    if not seen:
        seen = DCTaskSeen(
            user_id=current_user.id,
            task_id=task.id,
        )
        db.session.add(seen)

    if request.json.get('task') is True:
        seen.time_task = db.func.now()
    if 'cnt_comments' in request.json:
        seen.cnt_comments = request.json['cnt_comments']
        seen.time_comments = db.func.now()
    if 'cnt_files' in request.json:
        seen.cnt_files = request.json['cnt_files']
        seen.time_files = db.func.now()

    db.session.commit()

    return '', 204
