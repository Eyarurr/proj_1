import io
import os
import re
import datetime
import tempfile
import hashlib
from urllib.parse import urlsplit, urlunsplit, urljoin
import shutil

import segno
from werkzeug.utils import secure_filename
from unidecode import unidecode
from flask import request, abort, current_app, url_for, send_file, make_response
from flask_login import current_user, login_required
from flask_babel import gettext
from lagring.exceptions import StorageException
from sqlalchemy.orm.attributes import flag_modified
from PIL import Image
import datauri

from . import mod, api_response
from .common import select_dict, update_dict, load_tour_view, load_tour_edit, FieldsParam, try_coerce, delete_key_dict
from visual.core import db, upload_slots_service, queue_quick
from visual.models import User, Folder, Tour, Footage, ToursChangedJurisdiction, TourSeen, TourVideo
from visual.util import get_flow_file, get_upload_slot_dir
from visual.api3.common import BgJob
from ..models.meta import TourMetaInside


def expand_fields(fields_param):
    fields = set(fields_param.split(','))
    if 'default' in fields:
        fields.remove('default')
        fields.update(['id', 'created', 'footage_id', 'folder_id', 'hidden', 'title', 'preview', 'password', 'shareable'])
    if 'gallery' in fields:
        fields.remove('gallery')
        fields.update(['gallery_user', 'gallery_admin', 'gallery_sort'])
    if 'traffic' in fields:
        fields.remove('traffic')
        fields.update(['traffic_today', 'traffic_total'])
    if 'baseurls' in fields:
        fields.remove('baseurls')
        fields.update(['tour_baseurl', 'footage_baseurl'])

    return fields


def tour_api_repr(tour, fields, **kwargs):
    """Возвращает словарь со свойствами тура, согласно набору полей в fields и список варнингов.
    :param tour: Tour
    :param fields: iterable
    :return: dict
    """
    tour_properties = (
        'id', 'created', 'updated', 'footage_id', 'user_id', 'folder_id', 'hidden', 'title', 'password_in_url',
        'gallery_user', 'gallery_admin', 'gallery_sort', 'meta', 'traffic_today', 'traffic_total'
    )
    footage_properties = ('id', 'type', 'status', 'created', 'updated', 'meta')
    meta_full = tour.meta_full(pseudo_properties=False)
    res = {}
    warnings = []
    for field in fields:
        val = None
        if field in tour_properties:
            val = getattr(tour, field)
        elif field in ('preview', 'screen'):
            val = getattr(tour, field).url
        elif field == 'features':
            val = tour.features_strings()
        elif field == 'paid_features':
            val = {f.feature: f.paid_till for f in tour.paid_features_rel}
        elif field == 'paid_features_time_left':
            val = tour.paid_features_time_left()
        elif field == 'shareable':
            val = tour.shareable()
        elif field == 'password':
            val = tour.password_hash is not None
        elif field == 'meta_full':
            val = meta_full
        elif field == 'cnt_skyboxes':
            val = tour.footage.count_panoramas()
        elif field == 'tour_baseurl':
            if tour.files:
                val = tour.files.url + '/'
            else:
                # Это — костыль, потому что некоторые (все) версии плееров не запускают туры, если tour_baseurl == null
                # Костыль нужно убрать 29 декабря 2021 года.
                val = 'https://biganto.com/'
        elif field == 'footage_baseurl':
            if tour.footage.files:
                val = tour.footage.files.url + '/'
        elif field == 'player_url':
            val = url_for('front.tour', tour_id=tour.id)
        elif field == 'player_url_abs':
            val = url_for('front.tour', tour_id=tour.id, _external=True)
        elif field == 'player_url_pwd':
            val = url_for('front.tour', tour_id=tour.id, password_hash=tour.password_hash)
        elif field == 'player_url_abs_pwd':
            val = url_for('front.tour', tour_id=tour.id, password_hash=tour.password_hash, _external=True)
        elif field == 'gallery_tags':
            val = [t.tag for t in tour.gallery_tags]
        elif field == 'seen_by_me':
            val = tour.seen_by_me.seen if tour.seen_by_me is not None else None
        elif field == 'cnt_videos':
            val = tour.cnt_videos
        elif field == 'folder.title' and tour.folder:
            val = tour.folder.title

        elif field.startswith('meta.'):
            try:
                val = select_dict(tour.meta, field[5:])
            except KeyError:
                warnings.append(gettext('Unknown field %(field)s', field=field))
                continue
        elif field.startswith('meta_full.'):
            try:
                val = select_dict(meta_full, field[10:])
            except KeyError:
                warnings.append(gettext('Unknown field %(field)s', field=field))
                continue

        elif field.startswith('footage.meta.'):
            footage_meta_field = field[13:]
            try:
                val = select_dict(tour.footage.meta, footage_meta_field)
            except KeyError:
                warnings.append(gettext('Unknown field %(field)s', field=field))
                continue
            res.setdefault('footage', {})
            res['footage'][field[8:]] = val
            continue
        elif field.startswith('footage.') and field[8:] in footage_properties:
            footage_field = field[8:]
            val = getattr(tour.footage, footage_field)
            if val is not None:
                res.setdefault('footage', {})
                res['footage'][footage_field] = val
                continue

        else:
            warnings.append(gettext('Unknown field %(field)s', field=field))
            continue

        res[field] = val

    return {**res, **kwargs}, warnings


def make_file_entry(model, url):
    """
    Канонизирует url (воспринимая его как наш псевдотип url для метаданных).
    Если может, находит файл на диске, соответствующий урлу и считает его размер.
    Возвращает словарь {'url': canonized_url, ['size': file_size]}
    """
    biganto_host = current_app.config.get('SERVER_NAME')
    if not biganto_host:
        biganto_host = request.headers.get('Host', 'biganto.com')

    entry = {}

    parts = urlsplit(url)

    path = None

    # Канонизируем URL и пытаемся понять, где лежит файл (только в относительных урлах и без указания домена)
    # 1. Относительный URL.
    if parts.netloc == '':
        # 1.1 /static/image.png -> https://biganto.com/static/image.png
        if parts.path.startswith('/'):
            entry['url'] = urlunsplit(['https', biganto_host, parts.path, parts.query, ''])

            roots = {
                '/assets/': current_app.config.get('ASSET_STORAGE_ROOT', '/tmp'),
                '/static/': current_app.static_folder
            }
            for prefix, root in roots.items():
                if parts.path.startswith(prefix):
                    path = os.path.join(root, parts.path[len(prefix):])
                    break

        # 1.2: 1536/1-0.jpg -> https://biganto.com/assets/footages/files/abcdef/1536/1-0.jpg
        #      models/model-0.obj -> http://cdn.com/footages/files/abcdef/models/model-0.obj
        else:
            # Делаем абсолютным model.files.url
            files_parts = urlsplit(model.files.url.rstrip('/') + '/')
            if files_parts.scheme == '':
                files_parts = files_parts._replace(scheme='https')
            if files_parts.netloc == '':
                files_parts = files_parts._replace(netloc=biganto_host)

            entry['url'] = urljoin(urlunsplit(files_parts), url)

            path = model.in_files(parts.path)

    # 2. Абсолютный урл
    else:
        entry['url'] = urlunsplit(parts)

    if path:
        try:
            entry['size'] = os.stat(path).st_size
        except (IOError, FileNotFoundError) as e:
            current_app.logger.error('api.tours_files: os.stat({}): {}'.format(path, str(e)))

    return entry


def update_tour(tour, payload):
    """Изменяет свойства тура согласно спецификации API 3.0 в части POST /tours и PUT /tours.
    При изменении folder_id проверяет, что папка принадлежит тому же юзеру, что и тур.
    Возвращает список предупреждений
    """
    warnings = []
    # Редактируемые свойства Tour
    tour_properties = {'footage_id': int, 'title': str, 'hidden': bool, 'gallery_user': bool, 'password_in_url': bool, "meta": dict}

    for key, value in payload.items():
        if key in tour_properties:
            try:
                setattr(tour, key, tour_properties[key](value))
            except ValueError:
                abort(400, gettext('Bad data type for property %(property)s', property=key))

        elif key == 'folder_id':
            if value is not None:
                try:
                    value = int(value)
                except ValueError:
                    abort(400, gettext('Bad data type for property %(property)s', property='folder_id'))
                # Если изменили folder_id, то проверяем, что новая папка существует и принадлежит тому же юзеру
                folder = Folder.query.get_or_404(value, description=gettext('Target folder not found.'))
                if folder.user_id != tour.user_id:
                    abort(403, gettext('You can not move tour %(tour)s to folder %(folder)s because folder %(folder)s does not belong to you.', tour=str(tour.title), folder=str(folder.title)))
            tour.folder_id = value

        elif key == 'password':
            if value is not None:
                tour.password_hash = Tour.hash_password(value)
            else:
                tour.password_hash = None

        elif key == 'screen@flow':
            if 'screen@dataurl' in payload:
                abort(400, gettext('You can not specify %(key1)s and %(key2)s simultaneously in one request.', key1='screen@flow', key2='screen@dataurl'))

            src, token, filename = get_flow_file(payload, 'screen@flow')
            try:
                tour.screen = os.path.join(src)
                tour.preview = os.path.join(src)
            except StorageException:
                abort(400, 'Unable to import image {}/{}: file not found, bad format or too small.'.format(token, filename))

        elif key == 'screen@dataurl':
            if 'screen@flow' in payload:
                abort(400, gettext('You can not specify %(key1)s and %(key2)s simultaneously in one request.', key1='screen@dataurl', key2='screen@flow'))

            try:
                uri = datauri.DataURI(value)
            except ValueError:
                abort(400, gettext('Malformed %(key)s value.', key=key))

            _, src = tempfile.mkstemp()
            with open(src, 'wb') as fh:
                fh.write(uri.data)
            try:
                tour.screen = os.path.join(src)
                tour.preview = os.path.join(src)
            except StorageException:
                abort(400, 'Unable to set tour preview: image has bad format or too small.')
            os.remove(src)

        elif key == 'assets':
            # Поддерживаем value = "upload-slot@hostname/SLOT"
            if value.startswith('upload-slot@'):
                server, slot, src_dir = get_upload_slot_dir(value)
                tour.mkdir()
                dst_dir = tour.in_files()

                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
                upload_slots_service.delete_slot(server, slot)
            else:
                abort(400, gettext('Malformed %(key)s value.', key='assets'))

        elif key.startswith('meta.'):
            try:
                update_dict(tour.meta, key[5:], value)
            except KeyError:
                warnings.append('Property {} not found.'.format(key))
            flag_modified(tour, 'meta')

        else:
            warnings.append('Property {} not found.'.format(key))

    return warnings


@mod.route('/my/tours')
@login_required
def get_my_tours():
    """GET /my/tours
    Получить список моих туров. То же самое, что и GET /tours, но с предустановленным GET-параметром user_id.
    """
    return get_tours(current_user.id)


@mod.route('/tours')
def get_tours(user_id=None):
    """GET /tours
    Получить список туров.
    GET-параметры:
        ?user_id: туры какого юзера брать. Обязательный параметр.
        ?folder_id: из какой папки этого юзера брать туры. По умолчанию туры берутся из корня. -1: отдать из всех папок.
        ?types: туры каких типов отдавать. По умолчанию: все
        ?fields: какие поля включить в ответ, через запятую, без пробелов. По умолчанию отдаются Tour.(id, created, footage_id, folder_id, hidden, title, preview.url)
        ?sort: сортировка: created, -created, updated, -updated, title, -title. По умолчанию: -created
    Ответ:
        [Tour, ...]
    """
    if user_id is None:
        user_id = request.args.get('user_id')
    folder_id = request.args.get('folder_id')
    types = request.args.get('types')
    statuses = request.args.get('statuses')
    fields = expand_fields(request.args.get('fields', 'default'))

    if not user_id:
        abort(400, 'Please specify user_id.')

    user = User.query.get_or_404(user_id, description='User not found.')

    if user.deleted and not (current_user.is_authenticated and current_user.has_role('tours')):
        abort(404, 'User deleted his account.')

    if user.banned and not (current_user.is_authenticated and current_user.has_role('tours')):
        abort(403, 'User is banned.')

    if folder_id and folder_id != '-1':
        # Проверяем существование папки, если она указана
        Folder.query.filter_by(user_id=user.id, id=folder_id).first_or_404(description='Folder not found.')

    # Строим запрос
    q = db.session.query(Tour) \
        .join(Footage) \
        .outerjoin(Folder) \
        .options(db.contains_eager(Tour.footage)) \
        .options(db.contains_eager(Tour.folder)) \
        .filter(Tour.user_id == user.id)

    if current_user.is_authenticated:
        q = q.add_column(TourSeen).outerjoin(TourSeen, db.and_(TourSeen.tour_id == Tour.id, TourSeen.user_id == current_user.id))
    else:
        q = q.add_column(db.null())

    if 'cnt_videos' in fields:
        if current_user.is_authenticated:
            q = q.add_column(db.func.count(TourVideo.id)).outerjoin(TourVideo).group_by(Tour.id, Footage.id, Folder.id, TourSeen.tour_id, TourSeen.user_id)
        else:
            q = q.add_column(db.func.count(TourVideo.id)).outerjoin(TourVideo).group_by(Tour.id, Footage.id, Folder.id)
    else:
        q = q.add_column(db.null())

    # Папка
    if folder_id != '-1':
        q = q.filter(Tour.folder_id == folder_id)

    # Если смотрим туры другого юзера, то показываем только не-hidden-туры
    if not (current_user.is_authenticated and (current_user.id == user.id or current_user.has_role('tours'))):
        q = q.filter(Tour.hidden == False, Footage._status.in_(['testing', 'published']))

    # types
    if types:
        types = types.split(',')
        bad = set(types) - set(Footage.TYPES.keys())
        if bad:
            abort(400, 'Wrong types parameters: %s.' % ','.join(bad))
        q = q.filter(Footage.type.in_(types))

    # statuses
    if statuses:
        statuses = statuses.split(',')
        bad = set(statuses) - set(Footage.STATUSES.keys())
        if bad:
            abort(400, 'Wrong statuses parameters: %s.' % ','.join(bad))

    # Если смотрим туры другого юзера, то список статусов урезается до testing, published
    if not (current_user.is_authenticated and (current_user.id == user.id or current_user.has_role('tours'))):
        if statuses:
            statuses = set(statuses) & {'testing', 'published'}
        else:
            statuses = {'testing', 'published'}

    if statuses:
        q = q.filter(Footage._status.in_(list(statuses)))

    # Сортировка
    sort = request.args.get('sort')
    sorts = {
        'title': Tour.title,
        '-title': Tour.title.desc(),
        'created': Tour.created,
        '-created': Tour.created.desc(),
        'updated': Tour.updated,
        '-updated': Tour.updated.desc()
    }
    if sort == 'title' and folder_id == '-1':
        q = q.order_by(Folder.title, sorts.get(sort, Tour.created.desc()))
    elif sort == '-title' and folder_id == '-1':
        q = q.order_by(Folder.title.desc(), sorts.get(sort, Tour.created.desc()))
    else:
        q = q.order_by(sorts.get(sort, Tour.created.desc()))

    result = []
    warnings = []
    for tour, seen, cnt_videos in q.all():
        tour.seen_by_me = seen
        tour.cnt_videos = cnt_videos
        api_repr, warn = tour_api_repr(tour, fields)
        warnings += warn
        result.append(api_repr)

    return api_response(result, warnings=warnings)


@mod.route('/my/tours', methods=('POST', ))
@login_required
def post_my_tours():
    return post_tours(current_user.id)


@mod.route('/tours', methods=('POST', ))
@login_required
def post_tours(user_id=None):
    """POST /tours
    Создать тур."""
    if user_id is None:
        user_id = request.json.get('user_id')

    if user_id:
        user_id = try_coerce(user_id, int, 'user_id')
        user = User.query.filter_by(id=user_id).first()
        if user is None:
            abort(400, 'User id="{}" not found.'.format(user_id))
    else:
        user = current_user

    if user.id != current_user.id and not current_user.has_role('tours'):
        abort(403, 'You can not create tours for other users.')

    if user.deleted:
        abort(403, 'You can not create tours for deleted users.')

    if 'footage_id' in request.json and 'footage' in request.json:
        abort(400, 'You can not specify both footage_id and footage in input data.')

    if 'footage_id' not in request.json and 'footage' not in request.json:
        abort(400, 'You should specify either footage_id or footage in input data.')

    tour = Tour(user_id=user.id)
    update_tour(tour, request.json)

    if 'footage' in request.json:
        footage = Footage(user_id=user.id)
        for key, coerce in {'type': str, 'status': str, 'meta': dict}.items():
            if key in request.json['footage']:
                try:
                    setattr(footage, key, coerce(request.json['footage'][key]))
                except ValueError:
                    abort(400, gettext('Bad data type for property %(property)s', property='footage' + key))
        db.session.add(footage)
        db.session.flush()
        tour.footage = footage

    db.session.add(tour)
    db.session.commit()
    tour.save_features()

    return api_response(tour.api_view())


@mod.route('/tours/<int:tour_id>')
def get_tour(tour_id):
    """GET /tours/<tour_id>
    Получить свойства одного тура.
    GET-параметры:
        ?fields: какие поля включить в ответ, через запятую, без пробелов. По умолчанию отдаются Tour.(id, created, footage_id, folder_id, hidden, title, preview.url)
    Ответ:
        Tour
    """
    tour = load_tour_view(tour_id, load_seen=True)

    fields = expand_fields(request.args.get('fields', 'default'))

    result, warnings = tour_api_repr(tour, fields)
    # result['seen'] = seen.seen

    return api_response(result, warnings=warnings)


@mod.route('/tours/<int:tour_id>', methods=('PUT', ))
@login_required
def put_tour(tour_id):
    """PUT /tours/<tour_id>
    Сохранить свойства одного тура.
    Ответ:
        Tour
    """
    tour = load_tour_edit(tour_id)

    warnings = update_tour(tour, request.json)
    tour.save_features()
    db.session.commit()

    fields = expand_fields(request.args.get('fields', 'default'))

    result, repr_warnings = tour_api_repr(tour, fields)
    warnings += repr_warnings

    return api_response(result, warnings=warnings)


@mod.route('/tours/<int:tour_id>/seen', methods=('POST', ))
def post_tour_seen(tour_id):
    """POST /tours/<tour_id>/seen
    Помечает тур как просмотренный текущим юзером и пишет время этого события в TourSeen.seen
    Ответ:
        пустой
    """
    tour = load_tour_view(tour_id)
    tour.set_seen()

    return '', 204


@mod.route('/tours/<int:tour_id>', methods=('DELETE', ))
@login_required
def delete_tour(tour_id):
    """DELETE /tours/<tour_id>
    Удалить тур.
    """
    tour = load_tour_edit(tour_id)
    tour.delete()
    db.session.commit()

    return '', 204


@mod.route('/tours/<int:tour_id>/copy', methods=('POST', ))
@login_required
def copy_tour(tour_id):
    """POST /tours/<tour_id>/copy
    Копирует тур и, если указано, съемку."""
    bgjobs = None
    tour = load_tour_view(tour_id)

    if not current_user.has_role('tours'):
        tours_count = db.session.query(db.func.count(Tour.id)).filter(Tour.user_id == current_user.id).scalar()
        tours_limit = current_user.tours_limit()
        if tours_count >= tours_limit:
            abort(403, 'You can not copy this tour, tours limit exceeded.')

    if not current_user.has_role('tours') and tour.user_id != current_user.id:
        abort(403, 'You can not copy this tour, it\'s not yours.')

    # В какого пользователя копировать тур
    if request.json.get('user_id'):
        tgt_user_id = try_coerce(request.json['user_id'], int, 'user_id')

        if tgt_user_id != current_user.id and not current_user.has_role('tours'):
            abort(403, 'You can not copy tours to other accounts.')

        tgt_user = User.query.get(tgt_user_id)
        if tgt_user is None:
            abort(400, 'Target user {} not found.'.format(tgt_user_id))
    else:
        tgt_user = current_user

    if tgt_user.deleted:
        abort(403, 'You can not copy tours to deleted users.')

    # В какую папку копировать тур
    if 'folder_id' in request.json and request.json['folder_id'] is not None:
        tgt_folder_id = try_coerce(request.json['folder_id'], int, 'folder_id')

        tgt_folder = Folder.query.filter_by(id=tgt_folder_id, user_id=tgt_user.id).first()
        if tgt_folder is None:
            abort(400, 'Target folder not found.')
    elif 'folder_id' in request.json and request.json['folder_id'] is None:
        # Не оч красиво, но folder_id равный None задействован когда копируется в ту же папку
        # в админке также уже используется условное значение '0' для корневой папки
        tgt_folder_id = '0'
    else:
        tgt_folder_id = tour.folder_id

    if request.json.get('title'):
        new_title = request.json.get('title')
    else:
        new_title = tour.title

    copy_footage = try_coerce(request.json.get('copy_footage', 0), int, 'copy_footage')

    job = queue_quick.enqueue('visual.jobs.admin.copy_tour',
                              tour.id, new_title, copy_footage, True, tgt_folder_id, tgt_user.id,
                              result_ttl=current_app.config.get('REDIS_EXPIRE_TIME'),
                              description=f'{tour.id}-{new_title}',
                              job_id=f'copy_tour:{tour.id}-{new_title}',
                              job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'])

    if not job:
        abort(500, gettext("Unable to proceed: can not add task in queue"))
    else:
        bgjob = BgJob(status='queued', id=job.id, queue_length=len(queue_quick) + 1)
        bgjobs = [bgjob.api_repr()]

    return api_response(result={}, bgjobs=bgjobs)


@mod.route('/tours/<int:tour_id>/assets')
def get_tour_assets(tour_id):
    tour = load_tour_view(tour_id)

    resolution = request.args.get('viewport_width', 2048, type=int)
    footage = tour.footage
    # {['url': str, 'size': int}, ...]
    files = []
    total_size = 0
    footage_urls = set()
    tour_urls = set()

    # Скайбоксы
    res = footage.choose_res(resolution)
    for skybox_id, skybox in footage.meta.get('skyboxes', {}).items():
        for face in range(0, 6):
            if footage.meta.get('binocular'):
                eyes = ['', 'left/', 'right/']
            else:
                eyes = ['']
            for eye in eyes:
                face_url = '{}/{}{}-{}.jpg'.format(res, eye, skybox_id, face)
                if skybox.get('revision'):
                    face_url += '?' + str(skybox['revision'])
                footage_urls.add(face_url)

    # Модель
    if 'model' in footage.meta:
        footage_urls.add(footage.meta['model'])

        if 'mtl' in footage.meta and os.path.exists(footage.in_files(footage.meta['mtl'])):
            footage_urls.add(footage.meta['mtl'])
            with open(footage.in_files(footage.meta['mtl'])) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith('map_Ka') or line.startswith('map_Kd'):
                        footage_urls.add('models/{}'.format(line[7:].strip()))

    # Планировки этажей
    for floor in footage.meta.get('floors').values():
        if 'big' in floor:
            footage_urls.add(floor['big'])
        if 'small' in floor:
            footage_urls.add(floor['small'])

    # Озвучка (Audioclip.url)
    for clip in tour.meta.get('audio', {}).values():
        if 'url' not in clip:
            continue
        tour_urls.add(clip['url'])

    # Overlay.type='image'
    for overlay_id, overlay in tour.meta.get('overlays', {}).items():
        if overlay.get('type') == 'image':
            img = overlay.get('widget', {}).get('url')
            img_hover = overlay.get('widget', {}).get('url_hover')
            for overlay_img in (img, img_hover):
                if isinstance(overlay_img, str):
                    tour_urls.add(overlay_img)

    # Actions
    for action_id, action in tour.meta.get('actions', {}).items():
        if action.get('type') == 'sound':
            url = action.get('url')
            if isinstance(url, str):
                tour_urls.add(url)
        elif action.get('type') == 'video':
            for url in action.get('urls', {}).values():
                if isinstance(url, str):
                    tour_urls.add(url)

    # Button.img
    for button in tour.meta.get('toolbar', []):
        if 'img' in button:
            tour_urls.add(button['img'])

    # Navigation.img
    for nav in tour.meta.get('navigator', []):
        if 'img' in nav:
            tour_urls.add(nav['img'])

    # Branding.logo_help
    if 'branding' in tour.meta and tour.meta['branding'].get('logo_help'):
        tour_urls.add(tour.meta['branding']['logo_help'])

    # Splash.bg_url
    if tour.meta.get('splash') and isinstance(tour.meta.get('splash', {}).get('bg_url'), str):
        tour_urls.add(tour.meta['splash']['bg_url'])

    # Теперь канонизируем собранные урлы и кладём их в files.
    for item in footage_urls:
        entry = make_file_entry(footage, item)
        files.append(entry)
        total_size += entry.get('size', 0)

    for item in tour_urls:
        if not item:
            continue
        entry = make_file_entry(tour, item)
        files.append(entry)
        total_size += entry.get('size', 0)

    result = {
        'files': files,
        'total_size': total_size,
        'resolution': res
    }

    return api_response(result)


def list_model_files(model, fields, subdir):
    """Возвращает компоненты ответа (result, warnings) API для листинга ассета files модели model"""
    result = []
    warnings = []

    sdir = model.in_files(subdir)
    if os.path.commonprefix([model.in_files(), os.path.normpath(sdir)]) != model.in_files():
        abort(400, gettext('You can not view this directory.'))
    if not os.path.isdir(sdir):
        abort(400, gettext('Directory %(dir)s does not exist.', dir=subdir))

    for de in os.scandir(sdir):
        file_info = {
            'name': de.name,
        }
        if de.is_dir():
            file_info['name'] += '/'
        else:
            if 'fsize' in fields:
                file_info['fsize'] = de.stat().st_size

            if 'isize' in fields and any([de.name.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp')]):
                try:
                    with Image.open(de.path) as img:
                        file_info['isize'] = img.size
                except:
                    warnings.append('Broken image {}'.format(de.name))
                    pass

        if 'ctime' in fields:
            file_info['ctime'] = datetime.datetime.isoformat(datetime.datetime.fromtimestamp(de.stat().st_ctime))

        result.append(file_info)

    return result, warnings


@mod.route('/tours/<int:tour_id>/files')
@mod.route('/tours/<int:tour_id>/files/<path:subdir>')
def get_tour_files(tour_id, subdir=''):
    """
    GET /tours/<id>/files
    GET-параметры:
    ?dir - из какой поддиректории
    ?fields - список из name, fsize, ctime, isize (default: name)
    """

    tour = load_tour_view(tour_id)
    if not tour.files:
        return api_response([])

    fields = FieldsParam(request.args.get('fields', 'default'), {'default': ['name', 'ctime', 'fsize']})

    result, warnings = list_model_files(tour, fields, subdir)

    return api_response(result, warnings=warnings)


@mod.route('/tours/<int:tour_id>/files', methods=('PUT', ))
@mod.route('/tours/<int:tour_id>/files/<path:subdir>', methods=('PUT',))
@login_required
def put_tour_files(tour_id, subdir=''):
    """
    PUT /tour/<id>/files
    {
        "source@upload": "TOKEN/filename" | "TOKEN/*",
        "dst_name": str
    }
    """
    def _move(src, dst):
        try:
            shutil.copy(src, dst)
        except FileExistsError:
            abort(400, gettext('Can\'t save file.'))

    tour = load_tour_edit(tour_id)

    fields = FieldsParam(request.args.get('fields', 'default'), {'default': ['name', 'ctime', 'fsize']})

    try:
        token, src_name = request.json['source@upload'].split('/')
    except ValueError:
        abort(400, gettext(gettext('Malformed %(key)s value.', key='source@upload')))

    # src_dir
    src_dir = os.path.join(current_app.config['FLOW_UPLOAD_TMP_DIR'], token)
    if os.path.commonprefix([current_app.config['FLOW_UPLOAD_TMP_DIR'], os.path.normpath(src_dir)]) != current_app.config['FLOW_UPLOAD_TMP_DIR']:
        abort(400, gettext('Bad source directory.'))
    if not os.path.isdir(src_dir):
        abort(400, gettext('Can\'t find source directory %(token)s', token=token))

    # dst_dir, dst_name
    if not tour.files:
        tour.mkdir()
        db.session.commit()
    dst_dir = tour.in_files(subdir)
    if os.path.commonprefix([tour.in_files(), os.path.normpath(dst_dir)]) != tour.in_files():
        abort(400, gettext('Bad destination directory.'))
    try:
        os.makedirs(dst_dir, exist_ok=True)
    except FileExistsError:
        abort(400, gettext('Can\'t save file.'))
    dst_name = secure_filename(unidecode(request.json.get('dst_name', src_name)))

    # Пишем
    if src_name == '*':
        for de in os.scandir(src_dir):
            if not de.is_file():
                continue
            src = os.path.join(src_dir, de.name)
            dst = tour.in_files(subdir, de.name)
            if os.path.commonprefix([tour.in_files(), os.path.normpath(dst)]) != tour.in_files():
                abort(400, gettext('Bad target directory.'))

            _move(src, dst)
    else:
        src = os.path.join(src_dir, secure_filename(unidecode(src_name)))

        dst = tour.in_files(subdir, dst_name)
        if os.path.commonprefix([tour.in_files(), os.path.normpath(dst)]) != tour.in_files():
            abort(400, gettext('Bad target directory.'))

        _move(src, dst)

    result, warnings = list_model_files(tour, fields, subdir)

    return api_response(result, warnings=warnings)


@mod.route('/tours/<int:tour_id>/files/<path:target>', methods=('DELETE',))
@login_required
def delete_tour_files(tour_id, target=''):
    """
    DELETE /tours/<id>/files/<target>
    GET:
    - ?fields
    """
    tour = load_tour_edit(tour_id)

    fields = FieldsParam(request.args.get('fields', 'default'), {'default': ['name', 'ctime', 'fsize']})

    if not tour.files:
        abort(404, gettext('File %(file)s not found.', file=target))

    dst = tour.in_files(target)
    if os.path.commonprefix([tour.in_files(), os.path.normpath(dst)]) != tour.in_files():
        abort(404, gettext('File %(file)s not found.', file=target))

    if os.path.isdir(dst):
        abort(404, gettext('%(file)s is a directory.', file=target))

    if not os.path.exists(dst):
        abort(404, gettext('File %(file)s not found.', file=target))

    os.unlink(dst)

    result, warnings = list_model_files(tour, fields, os.path.dirname(target))

    return api_response(result, warnings=warnings)


@mod.route('/tours/changed_jurisdiction', methods=('POST', ))
@login_required
def changed_jurisdiction():
    if len({'local_id', 'remote_id', 'moved_to'} & set(request.json)) != 3:
        abort(400, 'You should specify local_id, remote_id, moved_to in input data.')

    if not current_user.has_role('tours'):
        abort(400, 'You have no rights to change tour jurisdiction.')

    tour = load_tour_edit(request.json['local_id'])
    remote_id = request.json.get('remote_id')
    moved_to = request.json.get('moved_to')

    if tour and remote_id and moved_to in current_app.config.get('JURISDICTIONS_HOSTS').keys():
        tour_changed = ToursChangedJurisdiction(
            local_id=tour.id,
            remote_id=remote_id,
            moved_to=moved_to
        )

        db.session.add(tour_changed)
        db.session.flush()
        db.session.commit()
    else:
        abort(400, 'Bad data in input data.')

    return api_response({
        'local_id': tour_changed.local_id,
        'remote_id': tour_changed.remote_id,
        'moved_to': tour_changed.moved_to
    })


@mod.route('/tours/<int:tour_id>/qr')
def generate_qrcode(tour_id):
    """GET-параметры:

format: формат картинки: 'png', 'svg'. default='png'.
version: версия QR-кода, число от 1 до 40. default=None.
error_correction: уровень коррекции ошибок, символ из набора ('L', 'M', 'Q', 'S'). default='M'.
scale: int оr float. размер одного квадратика в QR-коде. Для векторных может быть float. default=10.
border_size: int размер рамки в квадратиках QR-кода. default=0
return: что вернуть методу: ссылку на сгенерированный файл или содержимое этого файла? Строка 'url' или 'content'.
rebuild_cache: при значении параметра '1', файловый кеш принудительно перестраивается.
anchor: якорь к ссылке тура указывающий на точку тура.
"""

    def get_path_qr(tour_id):
        """Формируем правильный путь для сохранения qr; вид 0/0/5"""
        qr_path = '{:,}'.format(tour_id).replace(',', '/')
        if len(qr_path) <= 3:
            return '0/0/' + qr_path
        elif 6 >= len(qr_path) >= 4:
            return '0/' + qr_path
        else:
            return qr_path

    error_correction_list = ('L', 'M', 'Q', 'H')
    qr_properties = ('format', 'version', 'error_correction', 'scale', 'border_size', 'return', 'rebuild_cache')

    tour = load_tour_view(tour_id)

    format = request.args.get('format', 'png')
    scale = request.args.get('scale', 10)
    version = request.args.get('version', None)
    border_size = request.args.get('border_size', None)
    error_correction = request.args.get('error_correction', 'M')
    rebuild_cache = request.args.get('rebuild_cache', '0')
    anchor = request.args.get('anchor', None)

    if anchor:
        if not re.match(r'\d+_[+|-]?\d+_[+|-]?\d+_[+|-]?\d+_[+|-]?\d+$', anchor):
            abort(400, gettext('Malformed %(key)s value.', key='anchor'))

    if rebuild_cache in ('0', '1'):
        rebuild_cache = int(rebuild_cache)
    else:
        abort(400, gettext('Malformed %(key)s value.', key='rebuild_cache'))

    if version is not None:
        try:
            version = int(version)
            if version < 1 or version > 40:
                raise ValueError
        except ValueError:
            abort(400, gettext('Malformed %(key)s value.', key='version'))

    if error_correction not in error_correction_list:
        abort(400, gettext('Malformed %(key)s value.', key='error_correction'))

    if format not in ('png', 'svg'):
        abort(400, gettext('Malformed %(key)s value.', key='format'))

    # для векторных форматов qr scale может быть дробью, для png нет
    try:
        scale = float(scale)
    except ValueError:
        abort(400, gettext('Malformed %(key)s value.', key='scale'))
    if format == 'png':
        if not scale.is_integer():
            abort(400, gettext('The "scale" value for a raster qr can only accept integers.'))

    if border_size is not None:
        if border_size.isdigit():
            border_size = int(border_size)
        else:
            abort(400, gettext('Malformed %(key)s value.', key='border_size'))

    return_ = request.args.get('return', 'url')
    if return_ not in ('url', 'content'):
        abort(400, gettext('Malformed %(key)s value.', key='return'))

    # Формируем папки для qr; 0/0/5
    path_qr = get_path_qr(tour_id)
    # Формируем имя файла
    qr_hash = hashlib.md5(str({'version': version, 'error_correction': error_correction, 'scale': scale,'border_size': border_size, 'anchor': anchor}).encode())
    qr_name = f'qr-{qr_hash.hexdigest()}.{format}'
    # Формируем абсолютное имя файла
    qr_code_abspath = os.path.join(current_app.config.get('QR_DIR'), path_qr, qr_name)

    buff = io.BytesIO()

    # Проверяем существует ли абсолютный путь или пришел rebuild_cache равный 1
    if not os.path.exists(qr_code_abspath) or rebuild_cache == 1:
        try:
            # создаем систему каталогов
            os.makedirs(os.path.join(current_app.config.get('QR_DIR'), path_qr), exist_ok=True)
        except:
            abort(500, gettext('Internal error while creating cache directory.'))
        # генерим qr
        try:
            qr = segno.make(url_for('front.tour', tour_id=tour.id, _external=True, _anchor=anchor), version=version, error=error_correction)
        except Exception as e:
            abort(500, gettext('Internal error creating QR code: %(msg)s.', msg=str(e)))
        # Сохраняем qr в буфер
        qr.save(buff, kind=format, border=border_size, scale=scale)
        try:
            with open(qr_code_abspath, 'wb') as fh:
                fh.write(buff.getvalue())
        except:
            abort(500, gettext('Internal error saving QR code.'))

    # файл или ссылка
    # если в query_string было "return=url" то возвращаем путь до файла на нашем сервере
    if return_ == 'url':
        qr = url_for('static', filename=f'cache/qr/{path_qr}/{qr_name}', _external=True)
        result = {'url': qr}

        return api_response(result)
    else:
        # если не url то возвращаем содержимое как attachment
        # если файл был создан то отправляем его
        if buff.getvalue() != b'':
            response = make_response(buff.getvalue())
            response.headers['Content-Type'] = 'image/png'
            response.headers['Content-Disposition'] = f'attachment; filename={qr_name}'
            del buff
            return response
        else:
            try:
                return send_file(qr_code_abspath, as_attachment=True)
            except FileNotFoundError:
                abort(404, gettext('File not found.'))


@mod.route('/tours/<int:tour_id>/meta.<selector>', methods=('DELETE',))
@login_required
def delete_tour_meta_selector(tour_id, selector):
    """
    Удаляет из меты тура какое-либо свойство по селектору - selector1.selector2...
    """
    tour = load_tour_edit(tour_id)
    delete_key_dict(tour.meta, selector.split('.'))
    flag_modified(tour, 'meta')
    db.session.commit()
    return  '', 204