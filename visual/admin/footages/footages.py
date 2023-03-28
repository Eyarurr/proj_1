import io
import os
import json
import zipfile
import shutil
from datetime import datetime
import logging

from flask import render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified
import rq

from visual.core import db, queue, queue_quick
from visual.util import flash_errors
from visual.models import User, Footage, Tour
from .forms import FootageEditForm, FootageFilter
from .. import mod, roles_required


@mod.route('/footages/')
@mod.route('/users/<int:user_id>/footages/')
def footages(user_id=None):
    if user_id:
        user = User.query.get_or_404(user_id, description='Юзер не найден')
    else:
        user = None

    q = Footage.query.order_by(Footage.created.desc()) \
        .options(db.joinedload(Footage.tours))

    filters = FootageFilter(request.args)

    if user:
        q = q.filter(Footage.user_id == user.id)

    if filters.type.data:
        q = q.filter(Footage.type == filters.type.data)

    if filters.status.data:
        q = q.filter(Footage.status == filters.status.data)

    if filters.search.data and filters.search.data != '':
        return redirect(url_for('.footage_edit', footage_id=filters.search.data.strip()))

    footages = q.paginate(per_page=50, error_out=False)

    # Для объектов в статусе queued и processing собираем job'ы из очереди, чтобы показывать, что там происходит
    jobs = {}
    for footage in footages.items:
        if footage.status in ('queued', 'processing'):
            job_id = footage.meta.get('_' + footage.status, {}).get('job_id')

            if not job_id:
                continue
            try:
                jobs[footage.id] = queue.fetch_job(job_id)
            except rq.exceptions.NoSuchJobError:
                pass
            except Exception as e:
                flash('Были проблемы при получении queue job для съёмки {}: {}'.format(footage.id, str(e)), 'warning')

    return render_template('admin/footages/index.html', footages=footages, jobs=jobs, filters=filters, user=user)


def delete_rq_job(footage):
    """Ищет ID rq-задачи в footage.meta[_status] и удаляет её"""
    job_id = footage.meta.get('_' + footage.status, {}).get('job_id')
    if job_id:
        job = queue.fetch_job(job_id)
        if job:
            job.delete()


@mod.route('/footages/queue-cancel/', methods=('POST', ))
def footage_queue_cancel():
    """Удаляет съёмку из очереди сборки: возвращает ей статус loading, удаляет задачу в очереди.
    """
    footage = Footage.query.get_or_404(request.form.get('footage_id'))

    log = logging.getLogger('builder')
    log.warning('Юзер {} отменил сборку съёмки {} в админке'.format(current_user.email, footage.id))

    # Удаляем старую задачу
    delete_rq_job(footage)

    footage.status = 'loading'
    footage.meta.pop('_queued', None)
    footage.meta.pop('_processing', None)
    flag_modified(footage, 'meta')
    db.session.commit()

    return redirect(url_for('.footages'))


@mod.route('/footages/queue-requeue/', methods=('POST', ))
def footage_queue_requeue():
    """Перезапускает сборку съёмки: удаляет задачу, ставит задачу заново, ставит статут queued
    """
    footage = Footage.query.get_or_404(request.form.get('footage_id'))

    log = logging.getLogger('builder')
    log.warning('Юзер {} перезапустил сборку съёмки {} в админке'.format(current_user.email, footage.id))

    # Удаляем старую задачу
    delete_rq_job(footage)

    # Потому что visual.jobs.build_inside() принимает аргументом ID тура
    if len(footage.tours) == 0:
        flash('У съёмки должен быть хоть один тур, чтобы перезапустить его сборку.', 'danger')
        return redirect(url_for('.footages'))

    # Ставим новую задачу в очередь
    job = queue.enqueue('visual.jobs.wrappers.build_inside', footage.tours[0].id)
    if job is None:
        # Задача уже успела завершиться (скорее всего, какой-то хуйнёй)
        flash("Не удалось поставить задачу в очередь, хз почему.", 'danger')
        return redirect(url_for('.footages'))

    # Ставим статус и meta._queued для съёмки
    queue_length = len(queue) + 1  # Грязный хак, потому что для первой добавленной задачи почему-то len(queue) возвращает 0, для второй 1 и т.д.
    footage._status = 'queued'
    footage.meta.pop('_processing', None)
    footage.meta['_queued'] = {
        'job_id': job.id,
        'queue_length': queue_length,
        'since': datetime.now().isoformat()
    }

    flag_modified(footage, 'meta')
    db.session.commit()

    return redirect(url_for('.footages'))


def load_from_zip(footage, zip_file):
    """Создаёт съёмку из ZIP-файла.
    """
    with zipfile.ZipFile(zip_file) as zip:
        shutil.rmtree(footage.files.abs_path, ignore_errors=True)
        footage.mkdir(True)
        zip.extractall(footage.files.abs_path)
        json_dir = footage.in_files('meta.json')
        if os.path.exists(json_dir):
            with open(json_dir, 'r') as meta:
                footage.meta = json.loads(meta.read())
            os.remove(footage.in_files('meta.json'))
    footage._status = 'testing'
    flag_modified(footage, 'meta')

    # Синхронизируем туры со съёмками
    new_keys = {'floors': set(footage.meta.get('floors', {}).keys()),
                'skyboxes': set(footage.meta.get('skyboxes', {}).keys())}

    for tour in footage.tours:
        old_keys = {'floors': set(tour.meta.get('floors', {}).keys()),
                    'skyboxes': set(tour.meta.get('skyboxes', {}).keys())}
        for updated_field in ('floors', 'skyboxes'):
            for key in old_keys[updated_field] - new_keys[updated_field]:
                del tour.meta[updated_field][key]
            for key in new_keys[updated_field] - old_keys[updated_field]:
                tour.meta[updated_field][key] = {'title': ''}
        start_skybox = tour.meta.get('start', {}).get('skybox')
        if start_skybox and start_skybox not in new_keys['skyboxes']:
            del tour.meta['start']
        flag_modified(tour, 'meta')


@mod.route('/footages/<int:footage_id>/edit/', methods=('GET', 'POST'))
@roles_required('tours')
def footage_edit(footage_id):
    footage = Footage.query.options(db.joinedload('tours'), db.joinedload(Footage.creator)).get_or_404(footage_id)

    form = FootageEditForm(obj=footage)
    if form.validate_on_submit():
        form.populate_obj(footage)
        try:
            zip_file = request.files.get('files')
            if zip_file and zip_file.filename != '':
                load_from_zip(footage, zip_file)
                form.status.data = 'testing'
        except ValueError as e:
            flash('Ошибка в метаданных: %s' % str(e), 'danger')
        else:
            db.session.commit()
            if request.form.get('stay'):
                flash('Изменения сохранены', 'success')
            else:
                return redirect(url_for('.footages'))
    else:
        flash_errors(form)

    return render_template('admin/footages/edit.html', footage=footage, form=form)


@mod.route('/footages/<int:footage_id>/json/', methods=('GET', 'POST'))
@roles_required('tours')
def footage_json(footage_id=None):
    """
    Редактирование метаданных. Мету разберёт на свойства 1-го уровня шаблон, в ответе все эти свойства
    придут с именами "meta.{{ property_name }}
    """
    footage = Footage.query.options(db.joinedload('tours'), db.joinedload(Footage.creator)).get_or_404(footage_id)

    mode = request.args.get('mode')
    if mode != 'single':
        mode = 'split'

    if request.method == 'POST':
        errors = 0

        if mode == 'single':
            meta = json.loads(request.form.get('meta'))
        else:
            meta = {}
            for key, value in request.form.items():
                if not key.startswith('meta.'):
                    continue
                prop = key[5:]
                try:
                    meta[prop] = json.loads(value)
                except ValueError as e:
                    flash('Ошибка в метаданных свойства {}: {}'.format(prop, str(e)), 'danger')
                    errors += 1

        if not errors:
            footage.meta = meta
            flag_modified(footage, 'meta')
            db.session.commit()
            flash('Изменения сохранены', 'success')
            redirect(url_for('.footage_json', footage_id=footage.id))

    if mode == 'single':
        jsoned = json.dumps(footage.meta, indent=4, ensure_ascii=False, sort_keys=True)
    else:
        jsoned = {}
        indent = {
            'passways': None,
            'resolutions': None
        }
        for key, value in footage.meta.items():
            # раньше ещё делали ...encode().decode('unicode-escape') чтобы разъескейпить кириллицу,
            # насильно заескейпленную Постгресом
            jsoned[key] = json.dumps(value, indent=indent.get(key, 4), ensure_ascii=False, sort_keys=True)

    return render_template('admin/footages/json.html', footage=footage, jsoned=jsoned, mode=mode)


@mod.route('/footages/view/<int:footage_id>/')
def footage_view(footage_id):
    footage = Footage.query.get_or_404(footage_id)
    tour = Tour(meta={})
    tour.footage = footage

    tour.meta.setdefault('options', {}).update(current_app.config.get('PLAYER_DEFAULTS', {}))

    flash('Это не тур, это голая съёмка!', 'info')
    return render_template('front/tour/index.html', tour=tour)


@mod.route('/footages/<int:footage_id>/download/')
def footage_download(footage_id):
    footage = Footage.query.get_or_404(footage_id)

    job = queue_quick.enqueue('visual.jobs.admin.zip_footage', footage.id, current_user.id, job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'])
    if job is None:
        # Задача уже успела завершиться (скорее всего, какой-то хуйнёй)
        flash('Не удалось создать задачу на упаковку съёмки, что-то с очередями. Дёрните админов.', 'danger')
    else:
        flash('Съёмка упаковывается в ZIP. Когда она будет готова, вам на почту {} придёт ссылка на её скачивание.'.format(current_user.email), 'success')

    return redirect(url_for('.footage_edit', footage_id=footage.id))


@mod.route('/footages/<int:footage_id>/delete/', methods=('POST',))
@roles_required('tours')
def footage_delete(footage_id):
    footage = Footage.query.get_or_404(footage_id)

    flash('Съёмка {} удалена навсегда.'.format(footage.id), 'success')
    footage.delete()
    db.session.commit()

    if request.args.get('referer'):
        return redirect(request.args['referer'])

    return redirect(url_for('.footages'))
