from flask import request, abort, send_file
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import DCTaskFile, DCTaskSeen
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query
from . import load_project_membership_area_task


@mod.post('/devcon/projects/<int:project_id>/tasks/<int:task_id>/files')
@login_required
def post_devcon_tasks_files(project_id, task_id):
    """
    POST /devcon/projects/<id>/tasks/<id>/files
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    if not membership.has_role('admin', 'taskman', 'worker') and task.created_by != current_user.id and task.assigned_to != current_user.id:
        abort(403, gettext('You can not add files for this task.'))

    if type(request.json) is not list:
        abort(400, 'Malformed request body (send list of objects, not object).')

    comment = []
    result = []

    for body in request.json:
        if type(body) is not dict:
            abort(400, 'Malformed request body.')
        file = DCTaskFile(
            task=task,
            task_id=task.id,
            created_by=current_user.id
        )
        db.session.add(file)
        db.session.flush()
        file.update_from_api_request(body)
        task.cnt_files += 1
        db.session.commit()

        comment.append({
            'id': file.id,
            'preview': None if file.preview is None else file.preview.url,
            'url': file.file.url,
            'name': file.file_name,
            'title': file.title
        })

        result.append(file.api_repr())

    task.add_comment('files.created', comment)
    db.session.commit()

    return api_response(result)


@mod.get('/devcon/projects/<int:project_id>/tasks/<int:task_id>/files')
@login_required
def get_devcon_tasks_files(project_id, task_id):
    """
    GET /devcon/projects/<id>/tasks/<id>/files
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    q = DCTaskFile.query.filter(DCTaskFile.task_id == task.id)

    # Сортировка
    orders = {
        'created': DCTaskFile.created,
    }
    q = apply_sort_to_query(q, request.args.get('sort', 'created'), orders)

    # Лимит, оффсет
    offset = request.args.get('offset', type=int)
    if offset:
        q = q.offset(offset)
    limit = request.args.get('limit', 500, type=int)
    if limit:
        q = q.limit(limit)

    result = []
    for file in q.all():
        result.append(file.api_repr())

    return api_response(result)


@mod.get('/devcon/projects/<int:project_id>/tasks/<int:task_id>/files/<file_id>')
@login_required
def get_devcon_tasks_file(project_id, task_id, file_id):
    """
    GET /devcon/projects/<id>/tasks/<id>/files/<file_id>
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    file = DCTaskFile.query.filter(DCTaskFile.task_id == task.id, DCTaskFile.id == file_id).first_or_404(gettext('File not found.'))

    return api_response(file.api_repr())


@mod.get('/devcon/projects/<int:project_id>/tasks/<int:task_id>/files/<file_id>/download')
@login_required
def download_devcon_tasks_file(project_id, task_id, file_id):
    """
    GET /devcon/projects/<id>/tasks/<id>/files/<file_id>/download
    ?attachment=1 - добавить Content-Disposition: attachment;
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    file = DCTaskFile.query.filter(DCTaskFile.task_id == task.id, DCTaskFile.id == file_id).first_or_404(gettext('File not found.'))

    return send_file(file.file.abs_path, mimetype=file.file_type, as_attachment=request.args.get('attachment') == '1', download_name=file.file_name)


@mod.delete('/devcon/projects/<int:project_id>/tasks/<int:task_id>/files/<file_id>')
@login_required
def delete_devcon_tasks_files(project_id, task_id, file_id):
    """
    DELETE /devcon/projects/<id>/tasks/<id>/files/<file_id>
    """
    project, membership, area, task = load_project_membership_area_task(project_id, None, task_id)

    file = DCTaskFile.query.filter(DCTaskFile.task_id == task.id, DCTaskFile.id == file_id).first_or_404(gettext('File not found.'))

    if not membership.has_role('admin', 'taskman') and task.created_by != current_user.id and file.created_by != current_user.id:
        abort(403, gettext('You can not add files for tasks in this project.'))

    # В tasks_seen уменьшаем количество просмотренных файлов для тех, кто видел этот файл
    # (то есть заходил в файлы позже его создания)
    DCTaskSeen.query\
        .filter(DCTaskSeen.task_id == task.id, DCTaskSeen.time_files >= file.created)\
        .update({'cnt_files': DCTaskSeen.cnt_files - 1})
    del file.file
    del file.preview
    db.session.delete(file)
    task.cnt_files -= 1

    task.add_comment('files.deleted', [{
        'id': file.id,
        'name': file.file_name,
        'title': file.title
    }])

    db.session.commit()

    return '', 204

