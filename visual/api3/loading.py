"""
API сборщика туров.
"""

import re
from datetime import datetime
import os
import shutil
import logging

from flask import request, current_app, g, abort
from flask_login import current_user, login_required
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified
from PIL import Image

from . import mod, api_response
from .common import BgJob, load_tour_view, check_model_size
from ..models import Tour, Footage
from ..core import db, queue
from visual.util import unlink_calm, get_flow_file


def load_tour(tour_id):
    """Загружает тур, проверяя права юзера на него.
    Проверяет у него _loading.options.lang, и если он не соответствует g.lang, то меняет его."""
    if 'virtoaster' not in current_user.products:
        abort(400, gettext('You have no access to Virtoaster.'))

    tour = load_tour_view(tour_id, required_types=['virtual'], required_statuses=['loading'])

    dirty = False
    if '_loading' not in tour.footage.meta:
        tour.footage.meta['_loading'] = Footage.INIT_META_LOADING
        dirty = True

    if tour.footage.meta['_loading'].get('options', {}).get('lang') != g.lang:
        tour.footage.meta['_loading'].setdefault('options', {})['lang'] = g.lang
        dirty = True

    if dirty:
        flag_modified(tour.footage, 'meta')
        db.session.commit()

    return tour


def check_panorama(src, is_binocular, tour):
    """Проверяет панораму: расширение, разрешение. Возвращает список ошибок.
    Ожидаемое разрешение панорам считает из Footage.meta._loading.options.max_resolution,
    не найдя его, берёт дефолтное значение из переменной конфига VIRTOASTER_DEFAULT_RESOLUTION.
    """
    errors = []
    max_resolution = tour.footage.meta['_loading'].get('options', {}) \
        .get('max_resolution', current_app.config.get('VIRTOASTER_DEFAULT_RESOLUTION'))

    filename = os.path.basename(src)
    if not os.path.exists(src):
        return [gettext('File %(filename)s not found.', filename=filename)]

    # Проверяем расширение
    ext = os.path.splitext(src)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png'):
        errors.append(
            gettext('Unsupported image extension %(extension)s in file %(filename)s. File skipped.', extension=ext,
                    filename=filename))
    else:
        # Проверяем разрешение
        with Image.open(src) as img:
            if is_binocular:
                expected_res = (max_resolution * 12, max_resolution)
            else:
                expected_res = (max_resolution * 6, max_resolution)

            if max_resolution != current_app.config.get('VIRTOASTER_DEFAULT_RESOLUTION') and \
                    current_user.products['virtoaster'].plan_id not in current_app.config.get('PLANS_TO_SHOW_MAX_RESOLUTION'):
                errors.append(gettext('Select the plan that meets your requirements.'))

            if (img.width, img.height) != expected_res:
                errors.append(
                    gettext(
                        'Unsupported resolution in file %(filename)s. %(w)s x %(h)s instead of %(wres)s x %(hres)s. File skipped.',
                        filename=filename, w=img.width, h=img.height, wres=expected_res[0], hres=expected_res[1]
                    )
                )

    return errors


@mod.route('/tours/<int:tour_id>/virtual/loading/skyboxes', methods=('PUT',))
@login_required
def put_virtual_loading_skyboxes(tour_id):
    """
    PUT /tours/<id>/loading/skyboxes
    Загрузить панорамы. ID скайбоксов вычисляются из имени файла.
    Input
        {
            "upload_token": TOKEN
            "binocular": bool
        }
    """
    tour = load_tour(tour_id)
    meta = tour.footage.meta['_loading']
    meta.setdefault('skyboxes', {})

    upload_token = request.json.get('upload_token')
    if not upload_token:
        return abort(400, gettext('No upload_token in request body.'))

    is_binocular = request.json.get('binocular', False)

    warnings = []

    tour.footage.mkdir()
    src_dir = os.path.join(current_app.config['FLOW_UPLOAD_TMP_DIR'], upload_token)
    if not os.path.isdir(src_dir):
        abort(400, gettext('Can\'t find source directory %(token)s', token=upload_token))
    os.makedirs(tour.footage.in_files('_loading', 'skyboxes', 'lr'), exist_ok=True)

    # Переносим все файлы из FLOW_TMP/token/ в Footage.files/frames/{set_id}
    for item in os.scandir(src_dir):
        # Угадываем ID из имени файла
        r = re.search(r'(\d+)\.([^.]+)$', item.name, re.IGNORECASE)
        if not r:
            warnings.append(
                gettext('Unable to recognize filename %(filename)s, could not figure out image ID. File skipped.',
                        filename=item.name))
            continue

        skybox_id = str(int(r.group(1)))
        warns = check_panorama(item.path, is_binocular, tour)
        if warns:
            warnings += warns
            continue

        # Пишем в meta._loading.skyboxes[skybox_id] сведения о файле.
        if skybox_id not in meta['skyboxes']:
            meta['skyboxes'][skybox_id] = {}

        if is_binocular:
            key_name, key_size = 'lr_file_name', 'lr_size'
        else:
            key_name, key_size = 'file_name', 'size'
        meta['skyboxes'][skybox_id][key_name] = item.name
        meta['skyboxes'][skybox_id][key_size] = item.stat().st_size

        # Двигаем файл с исходником
        if is_binocular:
            dst_path = tour.footage.in_files('_loading', 'skyboxes', 'lr', item.name)
        else:
            dst_path = tour.footage.in_files('_loading', 'skyboxes', item.name)
        shutil.move(item.path, dst_path)

    flag_modified(tour.footage, 'meta')
    db.session.commit()

    # Стираем директорию загрузки
    shutil.rmtree(src_dir, ignore_errors=True)

    return api_response(meta['skyboxes'], warnings=warnings)


@mod.route('/tours/<int:tour_id>/virtual/loading/skyboxes/<skybox_id>', methods=('PUT',))
@login_required
def put_virtual_loading_skybox(tour_id, skybox_id):
    """
    PUT /tours/<tour_id>/virtual/loading/skyboxes/<skybox_id>

    Изменяет или создаёт скайбокс <skybox_id>.

    В теле запроса ожидает увидеть:
    {
        "file_name@flow": "TOKEN/filename" или null, чтобы удалить центральную панорамы
        "lr_file_name@flow": "TOKEN/filename" или null, чтобы удалить бинокулярную панорамы
        "pos": vector3
        "q": quaternion
    }
    """
    tour = load_tour(tour_id)
    tour.footage.mkdir()
    os.makedirs(tour.footage.in_files('_loading', 'skyboxes', 'lr'), exist_ok=True)
    meta = tour.footage.meta['_loading']

    skybox = meta['skyboxes'].setdefault(skybox_id, {})

    def put_skybox_panorama(file_param, size_param, tour, skybox, is_binocular):
        p = ['_loading', 'skyboxes']
        if is_binocular:
            p += ['lr']

        if request.json[file_param + '@flow'] is None:
            unlink_calm(tour.footage.in_files(*p, skybox[file_param]))
            skybox.pop(file_param, None)
            skybox.pop(size_param, None)
            return

        src, token, filename = get_flow_file(request.json, file_param + '@flow')

        errors = check_panorama(src, is_binocular, tour)
        if errors:
            abort(400, errors)

        # Если у этого скайбокса была панорама, то удаляем её
        if file_param in skybox:
            unlink_calm(tour.footage.in_files(*p, skybox['file_name']))

        # Если файл с таким же именем уже есть (например, в другом скайбоксе), находим незанятое имя файла
        dst = tour.footage.in_files(*p, filename)
        while os.path.exists(dst):
            filename = '_' + filename
            dst = tour.footage.in_files(*p, filename)

        shutil.move(src, dst)
        skybox[file_param] = filename
        skybox[size_param] = os.stat(dst).st_size

    if 'pos' in request.json:
        try:
            skybox['pos'] = [float(request.json['pos'][i]) for i in range(3)]
        except (ValueError, IndexError):
            abort(400, gettext('Bad data type for property %(property)s', property='pos'))

    if 'q' in request.json:
        try:
            skybox['q'] = [float(request.json['q'][i]) for i in range(4)]
        except (ValueError, IndexError):
            abort(400, gettext('Bad data type for property %(property)s', property='q'))

    if 'file_name@flow' in request.json:
        put_skybox_panorama('file_name', 'size', tour, skybox, False)

    if 'lr_file_name@flow' in request.json:
        put_skybox_panorama('lr_file_name', 'lr_size', tour, skybox, True)

    meta['skyboxes'][skybox_id] = skybox
    flag_modified(tour.footage, 'meta')
    db.session.commit()

    return api_response(meta['skyboxes'])


@mod.route('/tours/<int:tour_id>/virtual/loading/skyboxes/<skybox_id>', methods=('DELETE',))
@login_required
def delete_virtual_loading_skybox(tour_id, skybox_id):
    """
    DELETE /tour/<tour_id>/virtual/loading/<skybox_id>
    Удалить скайбокс.
    """
    tour = load_tour(tour_id)
    meta = tour.footage.meta['_loading']

    if skybox_id not in meta['skyboxes']:
        abort(404, gettext('Point %(skybox_id)s not found', skybox_id=skybox_id))

    skybox = meta['skyboxes'][skybox_id]
    if skybox.get('file_name'):
        unlink_calm(tour.footage.in_files('_loading', 'skyboxes', skybox['file_name']))
    if skybox.get('lr_file_name'):
        unlink_calm(tour.footage.in_files('_loading', 'skyboxes', 'lr', skybox['lr_file_name']))

    del meta['skyboxes'][skybox_id]

    flag_modified(tour.footage, 'meta')
    db.session.commit()

    return '', 204


@mod.route('/tours/<int:tour_id>/virtual/loading/model', methods=('PUT',))
@login_required
def tour_create_model(tour_id):
    """
    PUT /tours/<tour_id>/virtual/loading/model
    {
        'model@flow': 'TOKEN/filename'
    }
    """
    tour = load_tour(tour_id)
    tour.footage.mkdir()
    meta = tour.footage.meta['_loading']

    src, token, filename = get_flow_file(request.json, 'model@flow')

    src_dir = os.path.join(current_app.config['FLOW_UPLOAD_TMP_DIR'], token)
    if not os.path.exists(src):
        abort(400, gettext('Model file %(filename) not found.', filename=filename))

    # Проверяем размер модели
    model_error = check_model_size(src, meta.get('options', {}).get('model_lowpoly', False))
    if model_error:
        shutil.rmtree(src_dir, ignore_errors=True)
        abort(400, model_error)

    # Модель должна быть с расширением .obj, чтобы всякую хуйню не заливали
    if filename[-3:].lower() != 'obj':
        shutil.rmtree(src_dir, ignore_errors=True)
        abort(400, gettext('Unsupported 3d model extension. Model should have .OBJ file format.'))

    # Если была старая модель, то удаляем её
    if meta.get('models') and len(meta['models']) > 0:
        unlink_calm(tour.footage.in_files('_loading', 'models', meta['models'][0]['file_name']))

    os.makedirs(tour.footage.in_files('_loading', 'models'), exist_ok=True)
    dst = tour.footage.in_files('_loading', 'models', filename)
    shutil.move(src, dst)
    shutil.rmtree(src_dir, ignore_errors=True)

    meta['models'] = [{
        'file_name': filename,
        'size': os.stat(dst).st_size
    }]

    flag_modified(tour.footage, 'meta')
    db.session.commit()

    return api_response(meta['models'])


@mod.route('/tours/<int:tour_id>/virtual/loading/model', methods=('DELETE',))
@login_required
def tour_create_model_delete(tour_id):
    """
    DELETE /tours/<tour_id>/virtual/loading/model
    """
    tour = load_tour(tour_id)
    meta = tour.footage.meta['_loading']

    if meta['models'] and len(meta['models']) > 0:
        unlink_calm(tour.footage.in_files('_loading', 'models', meta['models'][0]['file_name']))
        del (meta['models'][0])
        flag_modified(tour.footage, 'meta')
        db.session.commit()

    return '', 204


@mod.route('/tours/<int:tour_id>/virtual/loading/build', methods=('POST',))
@login_required
def tour_create_build(tour_id):
    """
    Ставит тур в очередь сборки.
    """
    tour = load_tour(tour_id)
    log = logging.getLogger('builder')
    if tour.footage.status != 'loading' or '_loading' not in tour.footage.meta:
        abort(400, gettext('Unable to proceed: incorrect tour status or metadata, please contact support service.'))

    job = queue.enqueue('visual.jobs.wrappers.build_inside', tour.id,
                        job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'])
    if job is None:
        # Задача уже успела завершиться (скорее всего, какой-то хуйнёй)
        abort(500, gettext("Unable to proceed: can not add task in queue"))

    # Грязный хак, потому что для первой добавленной задачи почему-то len(queue) возвращает 0, для второй 1 и т.д.
    queue_length = len(queue) + 1
    tour.footage.status = 'queued'
    tour.footage.meta['_loading']['build_errors'] = []
    tour.footage.meta['_queued'] = {
        'job_id': job.id,
        'queue_length': queue_length,
        'since': datetime.now().isoformat()
    }
    flag_modified(tour.footage, 'meta')
    db.session.commit()

    log.info('Сборка тура {} в очереди'.format(tour.id))

    bgjob = BgJob(status='queued', id=job.id, queue_length=queue_length)

    return api_response({}, bgjobs=[bgjob.api_repr()])
