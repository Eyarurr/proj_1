import re
import os
import shutil

from typing import List
from flask_babel import gettext
from werkzeug.utils import secure_filename
from flask import request, abort, current_app
from sqlalchemy.orm.attributes import flag_modified
from flask_login import current_user, login_required

from . import mod, api_response
from .tours import list_model_files
from visual.models import User, Tour, Footage
from visual.api3.common import load_footage_edit, BgJob
from visual.core import db, upload_slots_service, queue_quick
from pydantic import BaseModel, validator, ValidationError, Extra
from visual.util import get_upload_slot_dir, get_flow_file, unlink_calm
from .common import select_dict, update_dict, FieldsParam, load_footage_view, check_model_size, \
    delete_key_dict, handle_asset_param


def expand_fields(fields_param):
    fields = set(fields_param.split(','))
    if 'default' in fields:
        fields.remove('default')
        fields.update(['id', 'created', 'updated', 'user_id', 'type', 'status'])

    return fields


def footage_api_repr(footage, fields):
    """Возвращает словарь со свойствами съёмки, согласно набору полей в fields.
    :param footage: Footage
    :param fields: iterable
    :return: dict
    """
    footage_properties = (
        'id', 'created', 'updated', 'user_id', 'type', 'status', 'meta'
    )
    res = {}
    warnings = []
    for field in fields:
        if field in footage_properties:
            val = getattr(footage, field)
        elif field == 'cnt_skyboxes':
            val = footage.count_panoramas()
        elif field.startswith('meta.'):
            try:
                val = select_dict(footage.meta, field[5:])
            except KeyError:
                warnings.append(gettext('Unknown field %(field)s', field=field))
                continue
        else:
            warnings.append(gettext('Unknown field %(field)s', field=field))
            continue

        res[field] = val

    return res, warnings


def update_footage(footage, obj):
    """Изменяет свойства тура согласно спецификации API 3.0 в части PUT /footages/<id>.
    Возвращает список предупреждений.
    """
    warnings = []
    # Редактируемые свойства Footage
    footage_properties = {"meta": dict}

    for key, value in obj.items():
        if key in footage_properties:
            try:
                setattr(footage, key, footage_properties[key](value))
            except ValueError:
                abort(400, gettext('Bad data type for property %(property)s', property=key))
        elif key == 'status':
            if value not in Footage.STATUSES.keys():
                abort(400, gettext('Bad status value'))
            try:
                footage.status = str(value)
            except ValueError:
                abort(400, gettext('Bad data type for property %(property)s', property=key))
        elif key == 'type':
            if value not in Footage.TYPES.keys():
                abort(400, gettext('Bad type value'))
            try:
                footage.type = str(value)
            except ValueError:
                abort(400, gettext('Bad data type for property %(property)s', property=key))
        elif key == 'assets':
            # Поддерживаем value = "upload-slot@hostname/SLOT"
            if value.startswith('upload-slot@'):
                server, slot, src_dir = get_upload_slot_dir(value)
                footage.mkdir()
                dst_dir = footage.in_files()

                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
                upload_slots_service.delete_slot(server, slot)
            else:
                abort(400, gettext('Malformed %(key)s value.', key='assets'))
        elif key.startswith('meta.'):
            try:
                update_dict(footage.meta, key[5:], value)
            except KeyError:
                warnings.append(gettext('Unknown input property %(property)s', property=key))
            flag_modified(footage, 'meta')

    return warnings


@mod.route('/footages/<int:footage_id>')
def get_footage(footage_id):
    """GET /footages/<footage_id>
    Отдаёт данные съёмки.
    """
    footage = load_footage_view(footage_id)
    fields = expand_fields(request.args.get('fields', 'default'))

    result, warnings = footage_api_repr(footage, fields)

    return api_response(result, warnings=warnings)


@mod.route('/footages/<int:footage_id>', methods=('PUT', ))
@login_required
def put_footage(footage_id):
    """PUT /footages/<footage_id>
    Сохранить данные съёмки.
    """
    footage = load_footage_edit(footage_id)

    if footage.user_id != current_user.id and not current_user.has_role('tours'):
        abort(403, gettext('You can not edit this tour.'))

    warnings = update_footage(footage, request.json)
    for tour in footage.tours:
        tour.save_features()
    db.session.commit()

    fields = expand_fields(request.args.get('fields', 'default'))
    result, repr_warnings = footage_api_repr(footage, fields)
    warnings += repr_warnings

    return api_response(result, warnings=warnings)


@mod.route('/footages/<int:footage_id>/files')
def get_footage_files(footage_id):
    """
    GET /footages/<id>/files
    GET-параметры:
    ?dir - из какой поддиректории
    ?fields - список из name, fsize, ctime, isize (default: name)
    """

    footage = load_footage_view(footage_id)
    if not footage.files:
        return api_response([])

    fields = FieldsParam(request.args.get('fields', 'default'), {'default': ['name']})
    dir_ = request.args.get('dir', '')

    result, warnings = list_model_files(footage, fields, dir_)

    return api_response(result, warnings=warnings)


@mod.route('/footages/<int:footage_id>/files/<path:path>', methods=('PUT', ))
@login_required
def put_footage_files(footage_id, path):
    footage = load_footage_edit(footage_id)
    result = {}

    # Приводим путь в порядок
    dirname, filename = os.path.split(path)
    filename = secure_filename(filename)
    path = os.path.join(dirname, filename)

    footage.mkdir()
    db.session.commit()  # Потому что в Footage.mkdir() может поменяться Footage._assets.

    dst = os.path.normpath(footage.in_files(path))
    if os.path.commonprefix([footage.in_files(), dst]) != footage.in_files():
        abort(403, 'You can not write files to this directory.')
    result['path'] = path

    # Создаём директорию
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    if request.headers.get('Content-Type') == 'application/octet-stream':
        # Пишем
        if request.headers.get('Content-Range'):
            content_range = request.headers['Content-Range']
            res = re.search(r'bytes (\d+)-(\d+)/(\d+)', content_range)
            if not res:
                abort(400, 'Malformed or unsupported Content-Range header. Should be like "bytes (\\d+)-(\\d+)/(\\d+)".')
            offset = int(res[1])
            length = int(res[2]) - offset
        else:
            offset = 0

        if not os.path.isfile(dst):
            fh = open(dst, 'wb')
            fh.close()

        with open(dst, 'r+b') as fh:
            fh.seek(offset)
            # @todo: брать request.stream и оттуда забирать не более length байт.
            data = request.get_data()
            fh.write(data)

    else:
        abort(400, 'Unsupported content type.')

    return api_response(result)


@mod.route('/footages/<int:footage_id>/passways/calc', methods=('POST',))
@login_required
def recalc_passways(footage_id):
    """
    Пересчитывает граф достижимости
    query string
    overwrite - перезаписывать passways в мете или нет : 1 перезаписывать 0 -нет
    {
    passways: [[s1, s2], [s1, s3], ...]
    }
    background - пересчитывать в фоне или нет: 1 в фоне  0 - нет
    {'bgjobs': ' ', 'result': {}}
    """
    def recalc_passways_enqueue(footage):
        bgjobs = None
        job = queue_quick.enqueue('visual.jobs.admin.calc_passways',
                                  footage.id, compare=None, no_recalc=None,
                                  result_ttl=current_app.config.get('REDIS_EXPIRE_TIME'),
                                  description=f'calc_passways: {footage.id}',
                                  job_id=f'calc_passways: footage-{footage.id}',
                                  job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'],
                                  )
        if not job:
            abort(500, gettext('Error saving coordinates. Please contact technical support.'))
        else:
            bgjob = BgJob(status='queued', id=job.id, queue_length=len(queue_quick) + 1)
            bgjobs = [bgjob.api_repr()]
        return bgjobs

    bgjobs = None
    result = {}
    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'),
                                required_statuses=('testing', 'published'))
    overwrite = request.args.get('overwrite', '0')
    background = request.args.get('background', '1')

    if overwrite not in ('0', '1'):
        abort(400, gettext('Malformed %(key)s value.', key='overwrite'))

    if background not in ('0', '1'):
        abort(400, gettext('Malformed %(key)s value.', key='background'))

    if overwrite == '0':
        if background == '1':
            if 'passways' in footage.meta and len(footage.meta['passways']) != 0:
                return '', 204
            else:
                bgjobs = recalc_passways_enqueue(footage)
        else:
            passways = footage.calc_passways()
            result['passways'] = passways

    else:
        if background == '0':
            passways = footage.calc_passways()
            footage.meta['passways'] = passways
            flag_modified(footage, 'meta')
            db.session.commit()
            result['passways'] = passways
        else:
            bgjobs = recalc_passways_enqueue(footage)

    return api_response(result=result, bgjobs=bgjobs)


@mod.route('/footages/<footage_id>/model_size/calc', methods=('POST',))
@login_required
def calc_model_size(footage_id):
    """
    Вычисляет значения Footage.meta.model_size и Footage.meta.model_size_gz. Возвращает объект вида
    {
        model_size: int,
        model_size_gz: int
    }
    """
    result = {}
    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'), required_statuses=('testing', 'published'))
    if not footage.meta.get('model', None):
        abort(400, gettext('No model in tour.'))

    if not os.path.exists(os.path.join(footage.in_files(), footage.meta['model'])):
        abort(400, gettext('Model file is missing.'))

    footage.meta['model_size_gz'], footage.meta['model_size'] = footage.get_gz_size()
    flag_modified(footage, 'meta')
    db.session.commit()

    result['model_size_gz'], result['model_size'] = footage.meta['model_size_gz'], footage.meta['model_size']
    return api_response(result)


@mod.route('/footages/<footage_id>/model', methods=('PUT', ))
@login_required
def footage_post_model(footage_id):
    """
    Устанавливает новую модель в тур, стирая старую. Увеличивает model_revision. Считает граф достижимости и размеры модели.
    Query String:
    * `filename` — имя файла для новой модели. Если параметр не указан или пуст, то модель будет называться по-умолчанию ("model-0.obj")
    * `background=1|0` — запускать ли процесс в фоне. Default=0.
    * `calc_passways=1|0` — считать ли граф достижимости. Default=1.
    Request body:
    {
        "model@flow": "TOKEN/filename"
    }

    """
    result = {}
    warnings = []

    footage = load_footage_edit(footage_id, required_types=('real', 'virtual'), required_statuses=('testing', 'published'))

    src, token, filename = get_flow_file(request.json, 'model@flow')

    # Проверяем размер модели. Разрешаем заливать модели не больше BUILDER_MODEL_SIZE_LIMIT[False]
    model_error = check_model_size(src, False)
    if model_error:
        src_dir = os.path.join(current_app.config['FLOW_UPLOAD_TMP_DIR'], token)
        shutil.rmtree(src_dir, ignore_errors=True)
        abort(400, model_error)

    # Если была старая модель, то стираем её (пригодится, если у новой будет новое имя) и увеличиваем model_revision
    if footage.meta.get('model'):
        unlink_calm(footage.in_files(footage.meta['model']))
        footage.meta.setdefault('model_revision', 0)
        footage.meta['model_revision'] += 1
        result['model_revision'] = footage.meta['model_revision']

    # Новое имя и путь модели
    new_filename = request.args.get('filename', 'model-0.obj')
    new_filename = secure_filename(new_filename)
    footage.mkdir()
    os.makedirs(footage.in_files('models'), exist_ok=True)
    dst = footage.in_files('models', new_filename)
    shutil.move(src, dst)
    footage.meta['model'] = 'models/' + new_filename
    result['model'] = footage.meta['model']

    # Считаем размеры модели
    footage.meta['model_size_gz'], footage.meta['model_size'] = footage.get_gz_size()
    result['model_size_gz'], result['model_size'] = footage.meta['model_size_gz'], footage.meta['model_size']

    # Считаем граф достижимости
    if request.args.get('calc_passways') != '0':
        try:
            passways = footage.calc_passways()
        except ValueError as e:
            passways = None
            warnings.append('Passways error: ' + str(e))
        footage.meta['passways'] = passways
        result['passways'] = footage.meta['passways']

    flag_modified(footage, 'meta')
    db.session.commit()

    return api_response(result, warnings=warnings)

@mod.route('/footages/<int:footage_id>/meta.<selector>', methods=('DELETE',))
@login_required
def delete_footage_meta_selector(footage_id, selector):
    """
    Удаляет из меты съемки какое-либо свойство по селектору - selector1.selector2...
    """
    footage = load_footage_edit(footage_id)
    delete_key_dict(footage.meta, selector.split('.'))
    flag_modified(footage, 'meta')
    db.session.commit()
    return  '', 204

class PostFootageArg(BaseModel, extra=Extra.forbid):
    user_id: int = None
    type: str = None
    status: str = None
    meta: dict = None
    assets: str = None
    tours_id: List[int] = None

    @validator('type')
    def check_type(cls, v):
        if v not in Footage.TYPES.keys():
            raise ValueError(f'Malformed type {v}')
        return v

    @validator('status')
    def check_status(cls, v):
        if v not in Footage.STATUSES.keys():
            raise ValueError(f'Malformed status {v}')
        return v


@mod.route('/footages', methods=('POST',))
@login_required
def footage_post():
    """
    "user_id": int,
    "type": str,
    "status": str(default testing),
    "meta": object={},
    "assets": "flow@TOKEN/*"
    """
    result = {}
    try:
        inp = PostFootageArg(**request.json)
    except ValidationError as e:
        return abort(400, gettext('API: bad input: {}'.format(e)))

    obj = { key: value for key, value in inp.dict().items() if value}
    if obj.get('user_id'):
        user = User.query.get_or_404(obj['user_id'], gettext('User not found.'))
    else:
        user = current_user

    if user.id != current_user.id and not current_user.has_role('tours'):
        abort(403, gettext('You can not create footage for other users.'))

    footage = Footage(user_id=user.id)
    db.session.add(footage)
    db.session.flush()
    result.update(footage.api_view())

    if obj.get('assets'):
        assets = obj.pop('assets')
        footage.mkdir()
        try:
            with handle_asset_param(assets, 'assets') as (fh, src):
                    for file in fh:
                        dst_dir = footage.in_files(file.name)
                        shutil.copytree(file.path, dst_dir, dirs_exist_ok=True)
        except ValueError as e:
            abort(400, gettext('Assets loading error: {}'.format(e)))
    update_footage(footage, obj)

    if obj.get('tours_id'):
        for tour_id in obj.get('tours_id'):
            tour = Tour.query.filter(Tour.id == tour_id).first_or_404(gettext('Tour not found'))
            if tour.user_id != current_user.id and not current_user.has_role('tours'):
                abort(403, gettext('You can not edit this tour.'))
            tour.footage_id = footage.id
            result.setdefault('tours', []).append(tour.api_view())
    db.session.commit()
    return api_response(result)