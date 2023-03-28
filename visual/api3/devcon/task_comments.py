from flask import request, abort
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCTaskComment, DCTaskSeen
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query
from . import load_project_membership_area_task


@mod.post('/devcon/projects/<int:project_id>/tasks/<int:task_id>/comments')
@login_required
def post_devcon_tasks_comments(project_id, task_id):
    """
    POST /devcon/projects/<id>/areas/<id>/comments
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    if not membership.has_role('admin', 'taskman', 'worker') and task.created_by != current_user.id and task.assigned_to != current_user.id:
        abort(403, gettext('You can not post comments for tasks in this project.'))

    comment = DCTaskComment(
        task=task,
        task_id=task.id,
        created_by=current_user.id,
        type='message'
    )
    comment.update_from_api_request(request.json)
    task.cnt_comments += 1
    db.session.add(comment)
    db.session.commit()

    return api_response(comment.api_repr())


@mod.get('/devcon/projects/<int:project_id>/tasks/<int:task_id>/comments')
@login_required
def get_devcon_tasks_comments(project_id, task_id):
    """
    GET /devcon/projects/<id>/areas/<id>/comments
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    q = DCTaskComment.query.filter(DCTaskComment.task_id == task.id)

    # Фильтр по типу
    if request.args.get('type'):
        filter_type = request.args['type']
        if filter_type.startswith('!'):
            filter_type = filter_type[1:]
            reverse = True
        else:
            reverse = False

        types = filter_type.split(',')

        if reverse:
            q = q.filter(DCTaskComment.type.not_in(types))
        else:
            q = q.filter(DCTaskComment.type.in_(types))

    # Сортировка
    orders = {
        'created': DCTaskComment.created,
    }
    q = apply_sort_to_query(q, request.args.get('sort', '-created'), orders)

    # Лимит, оффсет
    offset = request.args.get('offset', type=int)
    if offset:
        q = q.offset(offset)
    limit = request.args.get('limit', 500, type=int)
    if limit:
        q = q.limit(limit)

    result = []
    for comment in q.all():
        result.append(comment.api_repr())

    return api_response(result)


@mod.get('/devcon/projects/<int:project_id>/tasks/<int:task_id>/comments/<comment_id>')
@login_required
def get_devcon_tasks_comment(project_id, task_id, comment_id):
    """
    GET /devcon/projects/<id>/tasks/<id>/comments/<comment_id>
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    comment = DCTaskComment.query.filter(DCTaskComment.task_id == task.id, DCTaskComment.id == comment_id).first_or_404(gettext('Comment not found.'))

    return api_response(comment.api_repr())


@mod.delete('/devcon/projects/<int:project_id>/tasks/<int:task_id>/comments/<comment_id>')
@login_required
def delete_devcon_tasks_comment(project_id, task_id, comment_id):
    """
    DELETE /devcon/projects/<id>/tasks/<id>/comments/<comment_id>
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    comment = DCTaskComment.query.filter(DCTaskComment.task_id == task.id, DCTaskComment.id == comment_id).first_or_404(gettext('Comment not found.'))

    if not membership.has_role('admin', 'taskman') and task.created_by != current_user.id and comment.created_by != current_user.id:
        abort(403, gettext('You can not delete comments for tasks in this project.'))

    # В tasks_seen уменьшаем количество просмотренных комментов для тех, кто видел этот коммент
    # (то есть заходил в комменты позже его создания)
    DCTaskSeen.query\
        .filter(DCTaskSeen.task_id == task.id, DCTaskSeen.time_comments >= comment.created)\
        .update({'cnt_comments': DCTaskSeen.cnt_comments - 1})

    db.session.delete(comment)
    task.cnt_comments -= 1
    db.session.commit()

    return '', 204

