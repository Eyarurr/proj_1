import json
import threading
import time
import colors

from flask import request, abort, current_app
from flask.ctx import AppContext
from flask_login import current_user, login_required
from flask_babel import gettext

from visual.core import db
from visual.models import RemoteDataset, RemoteEvent, Footage, Tour, Folder, USFilincam
from visual import filincam
from . import mod, api_response


def get_dataset_main_props(rq):
    """
    Проверяет свойства `type`, `id`, `user_id` из тела запроса и возвращает их кортежем.
    Выбрасывает нужное исключение, если они хуёвые.
    Проверяет права доступа: если в запросе указано `user_id`, а текущий юзер не имеет роли `remote-processing`, то выкинет HTTP 403.
    `user_id` будет равен current_user.id, если не указан в запросе.
    :param rq: Объект тела запроса
    :return: (type, remote_id, user_id)
    """
    if 'type' not in rq or type(rq['type']) is not str or len(rq['type']) > RemoteDataset.type.type.length:
        abort(400, 'Bad Dataset.type value. Should be string shorter than {} bytes.'.format(RemoteDataset.type.type.length))
    type_ = rq['type']

    if 'id' not in rq or type(rq['id']) is not str or len(rq['id']) > RemoteDataset.remote_id.type.length:
        abort(400, 'Bad Dataset.id value. Should be string shorter than {} bytes.'.format(RemoteDataset.remote_id.type.length))
    remote_id = rq['id']

    if 'user_id' in rq:
        # Указали владельца датасета, проверяем права
        try:
            user_id = int(rq['user_id'])
        except TypeError:
            abort(400, 'Bad Dataset.user_id value. Should be integer or convertible to int.')
            return

        # Если указанный в запросе user_id не является ID текущего юзера, то разрешаем работать только юзерам с ролью remote-processing
        if current_user.id != user_id and not current_user.has_role('remote-processing'):
            abort(403, 'You can create or update datasets only for current user.')
    else:
        # Владелец не указан, поэтому считаем, что это датасет текущего юзера
        user_id = current_user.id

    return type_, remote_id, user_id


@mod.route('/my/remote-processing/datasets', methods=('GET', ))
@login_required
def my_get_remote_processing_datasets():
    return get_remote_processing_datasets(user_id=current_user.id)


@mod.route('/remote-processing/datasets', methods=('GET', ))
@login_required
def get_remote_processing_datasets(user_id=None):
    """
    GET /remote-processing/datasets
    GET /my/remote-processing/datasets
    Отдаёт список датасетов юзера:
    GET-параметры:
        ?user_id: Какого юзера отдавать датасеты. Чужие датасеты могут смотреть только юзеры с ролями remote-processing.*
        ?sort: Как сортировать список: created, last_event.created, type, title; Минус перед значением параметра означает обратное направление сортировки. Default='-created'
        ?offset: С какого элемента начинать (смещение). Default = 0.
        ?limit: Какое количество датасетов отдавать. Default = 50.
    Ответ:
        [Dataset, ...]
    :return:
    """
    if user_id is None:
        user_id = request.args.get('user_id', type=int)
    if user_id is None:
        abort(400, 'Please specify user_id.')

    if user_id != current_user.id and not current_user.has_role('remote-processing', 'remote-processing.view'):
        abort(403, 'You can not view other users datasets.')

    sort_orders = {
        'created': (RemoteDataset.created, RemoteDataset.id),
        '-created': (RemoteDataset.created.desc(), RemoteDataset.id.desc()),
        'last_event.created': (RemoteEvent.created.nulls_first(), RemoteDataset.created, RemoteDataset.id),
        '-last_event.created': (RemoteEvent.created.desc().nulls_last(), RemoteDataset.created.desc(), RemoteDataset.id),
        'type': (RemoteDataset.type.nulls_last(), RemoteDataset.created, RemoteDataset.id),
        '-type': (RemoteDataset.type.desc().nulls_last(), RemoteDataset.created.desc(), RemoteDataset.id),
        'title': (RemoteDataset.title.nulls_last(), RemoteDataset.created, RemoteDataset.id),
        '-title': (RemoteDataset.title.desc().nulls_last(), RemoteDataset.created.desc(), RemoteDataset.id),
    }
    sort = request.args.get('sort', '-created')
    if sort not in sort_orders:
        abort(400, 'Bad sort value.')

    try:
        offset = request.args.get('offset', 0, type=int)
    except TypeError:
        abort(400, 'Bad offset value.')
    if offset and offset < 0:
        abort(400, 'Bad offset value.')

    try:
        limit = request.args.get('limit', 50, type=int)
    except TypeError:
        abort(400, 'Bad limit value.')
    if limit and (limit < 0 or limit > 500):
        abort(400, 'Bad limit value.')

    cq = db.session.query(db.func.count(RemoteDataset.id)).filter(RemoteDataset.user_id == user_id)
    total = cq.scalar()

    q = RemoteDataset.query.outerjoin(RemoteEvent, RemoteDataset.last_event_id == RemoteEvent.id).options(db.contains_eager(RemoteDataset.last_event))
    q = q.filter(RemoteDataset.user_id == user_id)
    q = q.order_by(*sort_orders[sort])
    q = q.offset(offset).limit(limit)

    result = []
    for dataset in q.all():
        result.append(dataset.api_repr())

    return api_response(result, pagination={'total': total, 'offset': offset, 'limit': limit})


@mod.route('/remote-processing/datasets', methods=('POST', ))
@login_required
def post_remote_processing_datasets():
    """POST /remote-processing/datasets
    Создаёт датасет.
    Тело запроса: Dataset
    Ответ: Dataset
    """
    warnings = []

    # Проверяем и получаем определяющие датасет параметры из тела запроса
    type_, remote_id, user_id = get_dataset_main_props(request.json)

    # Смотрим, нет ли такого датасета уже в базе
    dataset = RemoteDataset.query.filter_by(type=type_, remote_id=remote_id).first()
    if not dataset:
        dataset = RemoteDataset(type=type_, remote_id=remote_id, user_id=user_id)
        db.session.add(dataset)
    else:
        warnings.append('Dataset "{}/{}" already exists, use PUT method.'.format(type_, remote_id))
        # У существующих датасетов запрещаем менять user_id
        if user_id != dataset.user_id:
            abort(403, 'Dataset already exist and you cannot modify Dataset.user_id value.')

    dataset.update_from_api_request(request.json)

    db.session.commit()

    return api_response(dataset.api_repr(), warnings=warnings)


@mod.route('/remote-processing/datasets/<dtype>/<path:dataset_id>', methods=('PUT', ))
@login_required
def put_remote_processing_datasets(dtype, dataset_id):
    """PUT /remote-processing/datasets
    Создаёт датасет.
    Тело запроса: Dataset
    Ответ: Dataset
    """
    warnings = []

    # Прверка входных данных
    rq = {'type': dtype, 'id': dataset_id}
    if 'user_id' in request.json:
        rq['user_id'] = request.json['user_id']
    type_, remote_id, user_id = get_dataset_main_props(rq)

    # Смотрим, нет ли такого датасета уже в базе
    dataset = RemoteDataset.query.filter_by(type=type_, remote_id=remote_id).first()
    if not dataset:
        warnings.append('Dataset "{}/{}" not found and was created, use POST method.'.format(type_, remote_id))
        dataset = RemoteDataset(type=dtype, remote_id=dataset_id, user_id=user_id)
        db.session.add(dataset)

    dataset.update_from_api_request(request.json)

    db.session.commit()

    return api_response(dataset.api_repr(), warnings=warnings)


@mod.route('/remote-processing/datasets/<dtype>/<path:dataset_id>', methods=('DELETE', ))
@login_required
def delete_remote_processing_datasets(dtype, dataset_id):
    """DELETE /remote-processing/datasets/<dataset_type>/<dataset_id>
    Удаляет датасет.
    """
    dataset = RemoteDataset.query.filter_by(type=dtype, remote_id=dataset_id).first()
    if not dataset:
        abort(404, 'Dataset not found.')

    if current_user.id == dataset.user_id or current_user.has_role('remote-processing'):
        db.session.delete(dataset)
        db.session.commit()
        return '', 204
    else:
        abort(404, 'Dataset not found.')


@mod.route('/my/remote-processing/datasets/count')
@login_required
def get_datasets_count():
    q = db.session.query(RemoteEvent.type, db.func.count('*')) \
        .join(RemoteDataset, RemoteDataset.last_event_id == RemoteEvent.id) \
        .filter(RemoteDataset.user_id == current_user.id) \
        .group_by(RemoteEvent.type)
    result = {}
    for etype, cnt in q.all():
        result[etype] = {'count': cnt}

    return api_response(result)


@mod.route('/remote-processing/datasets/<dtype>/<path:dataset_id>/events', methods=('POST', ))
@login_required
def post_remote_processing_event(dtype, dataset_id):
    """POST /remote-processing/datasets/<dataset_type>/<dataset_id>/events
    Регистрирует событие с датасетом.
    Тело запроса: RemoteEvent {type!, meta, job_id, ts}
    """
    warnings = []

    dataset = RemoteDataset.query.filter_by(type=dtype, remote_id=dataset_id).first()
    if not dataset:
        abort(404, 'Dataset not found.')

    # Обычные юзеры постят евенты только в свои датасеты
    if current_user.id != dataset.user_id and not current_user.has_role('remote-processing'):
        abort(404, 'Dataset not found.')

    event = RemoteEvent(dataset_id=dataset.id)
    event.update_from_api_request(request.json)
    if event.type not in current_app.config['REMOTE_EVENT_TYPES'].get(dataset.type, []):
        warnings.append('Event type "{}" is not supported for dataset type "{}"'.format(event.type, dataset.type))
    dataset.send_event(event)

    # Особые действия на события
    user = dataset.user
    if event.type == 'upload.success':
        if user.settings_obj.filincam.autoprocess:
            request_scene_processing(dataset, dataset.user.settings_obj.filincam)
            user.notify('filincam/upload_success_autoprocessed', {'dataset': dataset})
        else:
            user.notify('filincam/upload_success', {'dataset': dataset})
    elif event.type == 'upload.failed':
        user.notify(
            'filincam/upload_failed',
            {'dataset': dataset, 'errors': event.meta.get('errors', [])}
        )

    elif event.type == 'processing.failed':
        user.notify(
            'filincam/processing_failed',
            {'dataset': dataset, 'errors': event.meta.get('errors', []), 'warnings': event.meta.get('warnings', [])}
        )
    elif event.type in ('processing.warning', 'upload.warning', 'transfer.warning'):
        user.notify(
            'filincam/processing_warning', {'dataset': dataset, 'warnings': event.meta.get('warnings', [])}
        )

    elif event.type == 'transfer.success':
        try:
            tour = Tour.query.get(event.meta['results'][0]['entity_id'])
        except KeyError:
            tour = None
        user.notify('filincam/transfer_success', {'dataset': dataset, 'tour': tour})
    elif event.type == 'transfer.failed':
        user.notify(
            'filincam/transfer_failed',
            {'dataset': dataset, 'errors': event.meta.get('errors', [])}
        )
    # @todo: processing.warning
    # @todo: upload.warning
    # @todo: transfer.warning
    return api_response(event.api_repr(), warnings=warnings)


@mod.route('/remote-processing/datasets/<dtype>/<path:dataset_id>/process', methods=('POST', ))
@login_required
def post_remote_processing_process(dtype, dataset_id):
    """
    Просит удалённый процессинг обработать сцену филинкама.
    Тело запроса:
    {
        "export_tour": {
            "title": "...",
            "folder_id": 123,
            "blur_faces": true,
            "blur_plates": false
        }
    }

    """
    warnings = []

    dataset = RemoteDataset.query.filter_by(type=dtype, remote_id=dataset_id).first()
    if not dataset:
        abort(404, 'Dataset not found.')

    # Обычные юзеры собирают только свои датасеты
    if current_user.id != dataset.user_id and not current_user.has_role('remote-processing'):
        abort(404, 'Dataset not found.')

    options = current_user.settings_obj.filincam.clone()
    try:
        # @todo: Это костыль, потому что фронт шлёт export_tour.folder_id в виде строки. Поправить на фронте и убрать отсюда!!!
        if 'folder_id' in request.json.get('export_tour', {}) and request.json['export_tour']['folder_id'] is not None:
            request.json['export_tour']['folder_id'] = int(request.json['export_tour']['folder_id'])

        options.merge(request.json)
    except TypeError as e:
        abort(400, str(e))

    if options.export_tour.folder_id is not None and Folder.query.filter_by(user_id=dataset.user_id, id=options.export_tour.folder_id).first() is None:
        abort(400, 'Requested folder does not exists.')

    errors = request_scene_processing(dataset, options)
    if errors:
        abort(400, '\n'.join(errors))
    else:
        return api_response({}, warnings=warnings)


def request_scene_processing(dataset: RemoteDataset, options: USFilincam) -> list:
    """Формирует запрос на процессинг датасета RemoteDataset dataset с опциями options и отправляет
    его или запускает эмулятор процессинга. Недостающие опции сборки берёт из dataset.user.settings.
    Возвращает список текстов ошибок."""
    if current_app.config['ENV'] == 'development':
        # Запускаем эмулятор сборки
        delay = request.json.get('_emulator_event_delay', 1)
        thread = threading.Thread(target=emulate_processing, args=(current_app.app_context(), dataset.id, options, delay))
        thread.start()
        return []
    else:
        # Делаем запрос к процессингу
        remote_folder_id = None
        if options.export_tour.folder_id is not None:
            remote_folder_id = str(options.export_tour.folder_id)
        body = {
            'data_uid': dataset.remote_id,
            'properties': {
                'object_type': [1],
                'name': options.export_tour.title or 'Untitled',
                'remote_folder_id': remote_folder_id,
                'auto_upload': True,
                'attributes': {
                    'face_detect_enable': options.export_tour.blur_faces,
                    'licence_plate_detect_enable': options.export_tour.blur_plates,
                    'image_processing_mode': 1,
                },
            }
        }
        resp = filincam.api_request('POST', '/processing_scheduler/api/v1/object', body)

        if resp.status_code not in (200, 201):
            return ['Processing server fault. Please contact support.']
        else:
            return []


def emulate_processing(context: AppContext, dataset_id: str, options: USFilincam, delay: float):
    """Эмулятор процессинга."""
    with context:
        dataset = RemoteDataset.query.get(dataset_id)
        print(colors.magenta(f'PROCESSING EMULATOR: dataset_id={dataset_id}, options={options}"'))

        print(colors.magenta(f'PROCESSING EMULATOR: "processing.started" to "{dataset.remote_id}"'))
        dataset.send_event(type='processing.started')
        time.sleep(delay)

        print(colors.magenta(f'PROCESSING EMULATOR: "processing.progress" to "{dataset.remote_id}"'))
        dataset.send_event(type='processing.progress', meta={'stage': 'queued'})
        time.sleep(delay * 2)
        for i in range(0, 100, 5):
            print(colors.magenta(f'PROCESSING EMULATOR: "processing.progress {i/100}" to "{dataset.remote_id}"'))
            dataset.send_event(type='processing.progress', meta={'stage': 'processing', 'progress': i / 100})
            time.sleep(delay)

        print(colors.magenta(f'PROCESSING EMULATOR: "processing.success" to "{dataset.remote_id}"'))
        dataset.send_event(type='processing.success')
        time.sleep(delay)

        print(colors.magenta(f'PROCESSING EMULATOR: "transfer.started" to "{dataset.remote_id}"'))
        dataset.send_event(type='transfer.started')
        time.sleep(delay / 10)

        for i in range(0, 100, 20):
            print(colors.magenta(f'PROCESSING EMULATOR: "transfer.progress {i/100}" to "{dataset.remote_id}"'))
            dataset.send_event(type='transfer.progress', meta={'progress': i / 100})
            time.sleep(delay)

        # Создаём липовый тур
        footage = Footage(user_id=dataset.user_id, type='real', _status='testing')
        tour = Tour(user_id=dataset.user_id, folder_id=options.export_tour.folder_id, title=f'[EMULATED TOUR] {options.export_tour.title or "Untitled"}')
        tour.footage = footage
        db.session.add(footage)
        db.session.add(tour)
        db.session.commit()

        print(colors.magenta(f'PROCESSING EMULATOR: "transfer.success" to "{dataset.remote_id}"'))
        dataset.send_event(type='transfer.success', meta={'results': [{'entity_type': 'tour', 'entity_id': tour.id}]})


@mod.route('/remote-processing/filincam/upload', methods=('POST', ))
@login_required
def post_remote_processing_filincam_upload():
    """
    Метод вызывается, когда юзер готов начать выгрузку сцены и хочет получить реквизиты для этого.

    Тело запроса:
    {
        protocol: "flow",  // Сейчас поддерживается только flow-upload
        title: str,        // Название сцены, вводит юзер
        camera: {
            model: str,    // Модель камеры, вводит юзер
            sn: str,       // Серийник камеры, вводит юзер или парсится из данных съёмки
            data_id: str   // Магическое число, парсится из данных съёмки
        }
    }

    """
    warnings = []
    result = {}

    protocol = request.json.get('protocol')
    if protocol != 'flow':
        abort(400, gettext('Bad protocol type for data transmitting.'))

    title = request.json.get('title')
    if type(title) is not str or len(title) == 0:
        abort(400, gettext('Enter scene title.'))

    camera = request.json.get('camera')
    if type(camera) is dict:
        if type(camera.get('model')) is not str or len(camera['model']) == 0:
            abort(400, gettext('Please, enter full camera model name.'))
        if type(camera.get('sn')) is not str or len(camera['sn']) == 0:
            abort(400, gettext('Please, enter camera serial.'))
        if type(camera.get('data_id')) is not str or len(camera['data_id']) == 0:
            abort(400, gettext('Can not detect scene files. Perhaps you choose wrong files.'))
    else:
        abort(400, gettext('Please, enter camera model, camera serial and choose scene files.'))

    body = {
        'protocol': 'flow',
        'user': {
            'user_id': current_user.id,
            'remote_host': current_app.config['JURISDICTIONS_HOSTS'][current_app.config['JURISDICTION']]['host']
        },
        'camera': {
            'sn': camera['sn'],
            'model': camera['model'],
            'data_id': camera['data_id']
        },
        'meta': {
            'type': 'scene'
        },
        'object': {
            'title': title
        }
    }

    resp = filincam.api_request('POST', '/processing_loader/api/v1/load', body)

    if resp.status_code not in (200, 201):
        abort(resp.status_code, gettext('Error occurred while data loading: %(error)s', error=resp.reason))
    else:
        result = {
            'location': resp.headers['Location'],
            'token': resp.json().get('token'),
            'upload_slot': resp.json().get('data_uid')
        }
        location = '/processing_loader/api/v1/load/{}?access_token={}'.format(result['upload_slot'], result['token'])

        resp = filincam.api_request('PUT', location, {'load_status': 'loading'})
        if resp.status_code not in (200, 201, 204):
            abort(resp.status_code, gettext('Error occurred while data loading parameters renewal: %(error)s',
                                            error=resp.reason))


    return api_response(result, warnings=warnings)


@mod.route('/remote-processing/filincam/upload/<upload_slot>/progress', methods=('POST', ))
@login_required
def post_remote_processing_filincam_upload_progress(upload_slot):
    """
    Метод вызывается, когда необходимо сообщить о прогрессе выгрузки.

    Тело запроса:
    {
        token: str,      // Токен из ответа POST /remote-processing/filincam/upload
        progress: float  // Степень готовности в долях единицы
    }

    """
    warnings = []

    if type(upload_slot) is not str or len(upload_slot) == 0:
        abort(400, gettext('Wrong input data value.'))

    token = request.json.get('token')
    if type(token) is not str or len(token) == 0:
        abort(400, gettext('Wrong token value.'))

    progress = request.json.get('progress')

    try:
        float(progress)
    except ValueError:
        abort(400, gettext('Wrong progress value.'))

    url = '/processing_loader/api/v1/load/{}?access_token={}'.format(upload_slot, token)
    body = {
        'load_status': 'progress',
        'meta': {
            'progress': float(progress) * 100
        }
    }

    resp = filincam.api_request('PUT', url, body)
    if resp.status_code not in (200, 201, 204):
        abort(resp.status_code, gettext('Error occurred while data loading parameters renewal: %(error)s',
                                        error=resp.reason))

    return api_response({}, warnings=warnings)


@mod.route('/remote-processing/filincam/upload/<upload_slot>/complete', methods=('POST', ))
@login_required
def post_remote_processing_filincam_upload_complete(upload_slot):
    """
    Метод вызывается, когда нужно сообщить о том, что всё выгрузилось
    Тело запроса:
    {
        token: str,      // Токен из ответа POST /remote-processing/filincam/upload
    }
    """
    token = request.json.get('token')
    if type(token) is not str or len(token) == 0:
        abort(400, gettext('Wrong token value.'))
    resp = filincam.api_request('GET', f'/processing_loader/api/v1/load/{upload_slot}/check?access_token={token}', body=None)

    if resp.status_code == 200:
        if resp.text:
            if ('errors' in resp.json() and len(resp.json().get('errors')) > 0) or 'error' in resp.json():
                abort(400, gettext('Error occurred while checking data integrity: %(error)s',
                                   error=' '.join(resp.json().get('errors', '')) + resp.json().get('error', '')))
        url = f'/processing_loader/api/v1/load/{upload_slot}?access_token={token}'
        body = {'load_status': 'loaded'}
        resp = filincam.api_request('PUT', url, body)

        if resp.status_code in (200, 201, 204):
            return api_response({})

    abort(400, gettext('Error occurred while data loading parameters renewal: %(error)s', error=resp.reason))


@mod.route('/remote-processing/filincam/upload/<upload_slot>', methods=('DELETE', ))
@login_required
def delete_remote_processing_filincam_upload(upload_slot):
    """
    Метод вызывается если юзер прервал выгрузку на клиенте
    Тело запроса:
    {
        token: str,      // Токен из ответа POST /remote-processing/filincam/upload
    }
    """
    token = request.json.get('token')
    if type(token) is not str or len(token) == 0:
        abort(400, gettext('Wrong token value.'))
    
    body = {'load_status': 'canceled'}

    resp = filincam.api_request('PUT', f'/processing_loader/api/v1/load/{upload_slot}?access_token={token}', body=body)
    if resp.status_code in (200, 201, 204):
        return api_response({})

    abort(400, gettext('Error occurred while data loading parameters renewal: %(error)s', error=resp.reason))
