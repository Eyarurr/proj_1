"""
Сборка outside-туров. Все эндпоинты, кроме tour_create_outside, возвращают объект в JSON. В случае ошибки, этот объект
будет содержать свойство "errors" типа список. Эндпоинты что они возвращают: (все начинаются с `tour_create_outside_`):


  title             {problems: [], title: ''}
  resolutions       {problems: [], resolutions: []}
  model             {problems: [], model: '', model_size: 0}
  model_delete      {problems: []}
  set               {problems: [], set: Set}
  set_add           {problems: [], set: Set}
  set_delete        {problems: [], id: 0}
  frames_complete   {problems: [], set: Set}
  frames_delete     {problems: [], set: Set}

_
"""
import os
import shutil
import uuid
import re
import logging


from flask import render_template, redirect, flash, url_for, request, jsonify, current_app
from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.utils import secure_filename

from visual.models import Footage, Tour, User
from visual.core import db, queue
from visual.util import unlink_calm
from .. import mod, roles_required


def find_set(tour, set_id):
    """Находит и возвращает нужный сет в метаданных"""
    for id, target_set in tour.footage.meta['sets'].items():
        if str(target_set['id']) == str(set_id):
            return target_set
    return None


def match_frames_coords(set_):
    """Расставляет во фреймы Frame.pos, Frame.anglem Frame.fov, исходя из set.coords"""
    if 'coords' not in set_ or 'frames' not in set_:
        return
    for frame_id, frame in set_['frames'].items():
        if frame_id in set_['coords']:
            frame.update(set_['coords'][frame_id])
        else:
            frame.pop('pos', None)
            frame.pop('angle', None)
            frame.pop('fov', None)


def check_tour(tour, commit=True):
    """Проверяет тур на ошибки, записывает их в footage.meta['errors'] и возвращает список проблем.
    Совершает COMMIT, если не запретить это параметроv :param commit:"""
    problems = []
    meta = tour.footage.meta

    if not tour.title.strip():
        problems.append('Дайте туру имя.')

    if not meta.get('resolutions'):
        problems.append('Не определены разрешения.')

    if not meta.get('sets'):
        problems.append('Не определён ни один сет.')
    else:
        for set_ in meta['sets'].values():
            if not set_.get('center'):
                problems.append('У сета {} не определён центр вращения.'.format(set_['id']))
            if not set_.get('frames'):
                problems.append('У сета {} нет фреймов.'.format(set_['id']))
            else:
                # Фреймы без координат
                no_coords = []
                for frame_id, frame in set_['frames'].items():
                    if 'pos' not in frame:
                        no_coords.append(frame_id)
                if len(no_coords) == 1:
                    problems.append('У фрейма {} в сете {} нет координат.'.format(no_coords[0], set_['id']))
                elif len(no_coords) > 1:
                    problems.append(
                        'У фреймов {} в сете {} нет координат.'.format(', '.join(sorted(no_coords)), set_['id']))

                # Координаты без картинок
                if 'coords' in set_:
                    for frame_id in set_['coords'].keys():
                        if frame_id not in set_['frames']:
                            problems.append('Нет картинки для фрейма {} в сете {}'.format(frame_id, set_['id']))

    tour.footage.meta['problems'] = problems
    flag_modified(tour.footage, 'meta')

    if commit:
        db.session.commit()

    return problems


@mod.route("/users/<int:user_id>/tours/create/outside/new/")
@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/")
@roles_required('tours')
def tour_create_outside(user_id=None, tour_id=None):
    user = User.query.get_or_404(user_id, description='Пользователь не найден')

    if tour_id is None:
        # Создаём съёмку и тур. Один сет без фреймов.
        footage = Footage(
            user_id=user.id,
            created_by=current_user.id,
            type='outside',
            status='loading',
            meta={
                'resolutions': [[480, 480], [720, 720], [1080, 1080], [1200, 1200]],
                'sets': {'1': {'id': 1, 'frames': {}, 'sort': 1}},
                'sources': {}
            }
        )
        db.session.add(footage)
        db.session.flush()

        folder_id = request.args.get('folder_id')
        if folder_id == '' or folder_id == '0':
            folder_id = None

        tour = Tour(
            user_id=user.id,
            created_by=current_user.id,
            footage_id=footage.id,
            folder_id=folder_id,
            title='',
            meta={}
        )
        tour.footage = footage
        db.session.add(tour)
        db.session.flush()

        # Создаём директорию съёмки и sources внутри неё
        footage.mkdir()
        os.makedirs(footage.in_files('frames', '1'), exist_ok=True)

        db.session.commit()
        return redirect(url_for('.tour_create_outside', tour_id=tour.id, user_id=user_id))

    tour = Tour.query.options(db.joinedload(Tour.footage)).get_or_404(tour_id)

    if tour.footage.type != 'outside':
        flash('Это не outside-тур.', 'danger')
        return redirect(url_for('.tours'))

    if request.args.get('rebuild') and tour.footage.status == 'processing':
        tour.footage.status = 'loading'
        db.session.commit()

    if tour.footage.status != 'loading':
        flash('Этот тур находится не в стадии загрузки.', 'danger')
        return redirect(url_for('.tours'))

    check_tour(tour)
    return render_template(
        'admin/tours/create_outside.html', tour=tour, user_id=user_id,
        upload_token=str(uuid.uuid4())
    )


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/title/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_title(tour_id, user_id=None):
    """Сохраняет tour.title"""
    tour = Tour.query.get_or_404(tour_id)
    tour.title = request.form.get('title').strip()
    return jsonify({'title': tour.title, 'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/resolutions/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_resolutions(tour_id, user_id=None):
    """Сохраняет список разрешений."""
    tour = Tour.query.get_or_404(tour_id)

    tour.footage.meta['resolutions'] = []
    for strres in request.form.getlist('res'):
        res = [int(_) for _ in strres.split('x')]
        tour.footage.meta['resolutions'].append(res)
    tour.footage.meta['resolutions'].sort()

    flag_modified(tour.footage, 'meta')

    return jsonify({'resolutions': tour.footage.meta['resolutions'], 'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/model/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_model(tour_id, user_id=None):
    """Устанавливает загруженную через flow модель."""
    tour = Tour.query.get_or_404(tour_id)

    filename = secure_filename(request.form['filename'])
    src_dir = os.path.join(current_app.config.get('FLOW_UPLOAD_TMP_DIR', '/tmp'), request.form['upload_token'])
    src = os.path.join(src_dir, filename)
    os.makedirs(tour.footage.in_files('models'), exist_ok=True)
    dst = tour.footage.in_files('models', filename)
    shutil.move(src, dst)
    shutil.rmtree(src_dir, ignore_errors=True)

    tour.footage.meta['models'] = {'0': 'models/{}'.format(filename)}
    tour.footage.meta['model_size'] = os.stat(dst).st_size

    flag_modified(tour.footage, 'meta')

    return jsonify({
        'model': tour.footage.meta['models']['0'],
        'model_size': tour.footage.meta['model_size'],
        'problems': check_tour(tour)
    })


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/model/delete/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_model_delete(tour_id, user_id=None):
    """Удаляет модель."""
    tour = Tour.query.get_or_404(tour_id)

    if 'model' not in tour.footage.meta:
        return ''

    unlink_calm(tour.footage.in_files(tour.footage.meta['model']), fail_flash=True)
    del tour.footage.meta['model']
    tour.footage.meta.pop('model_size', None)

    flag_modified(tour.footage, 'meta')

    return jsonify({'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/set/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_set(tour_id, user_id=None):
    """Свойства сета: название, центр вращения."""
    tour = Tour.query.get_or_404(tour_id)
    set_id = request.form.get('id', type=int)
    target_set = find_set(tour, set_id)

    if target_set is None:
        return jsonify({'errors': ['Редактируемый сет не найден. Возможно, его кто-то удалил. Обновите страницу.']})

    # Название сета
    target_set['title'] = request.form.get('title').strip()

    # Валидируем и сохраняем центр вращения
    if request.form.get('center').strip() == '':
        target_set.pop('center', None)
    else:
        try:
            center = [float(_) for _ in request.form.get('center').split(',')]
        except ValueError:
            return jsonify({'errors': ['Неверная координата центра. Нужно в формате X, Y, Z']})
        target_set['center'] = center

    # Координаты
    if request.form.get('coords').strip() == '':
        target_set.pop('coords', None)
    else:
        # Парсим координаты
        coords = {}
        for i, line in enumerate(request.form.get('coords').split('\n')):
            line = line.strip()
            if line == '' or line.startswith('#'):
                continue
            try:
                id_, pos_, angle_, fov = line.split(';')
                id_ = id_.strip()
                coords[id_] = {
                    'pos': [float(_) for _ in pos_.split(',')],
                    'angle': [float(_) for _ in angle_.split(',')],
                    'fov': float(fov)
                }
            except ValueError:
                return jsonify(
                    {'errors': ['В тексте с координатами фреймов некорректная строка {}:\n{}'.format(i + 1, line)]})

        target_set['coords'] = coords

    match_frames_coords(target_set)

    flag_modified(tour.footage, 'meta')

    set_ = target_set.copy()
    for frame_id, frame in set_['frames'].items():
        frame['url'] = '{}/frames/{}/{}'.format(tour.footage.files.url, set_id, frame['filename'])

    return jsonify({'set': set_, 'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/set/add/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_set_add(tour_id, user_id=None):
    """Добавить сет."""
    tour = Tour.query.get_or_404(tour_id)

    # Ищем максимальный id
    set_id = max([x['id'] for id, x in tour.footage.meta['sets'].items()])
    set_id += 1

    # Создаём сет и директорию
    new_set = {'id': set_id, 'frames': {}, 'sort': set_id}
    tour.footage.meta['sets'][str(set_id)] = new_set
    os.makedirs(tour.footage.in_files('frames', str(set_id)))

    flag_modified(tour.footage, 'meta')

    return jsonify({'set': new_set, 'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/set/delete/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_set_delete(tour_id, user_id=None):
    """Удалить сет."""
    tour = Tour.query.get_or_404(tour_id)
    set_id = request.form.get('id', type=int)
    meta = tour.footage.meta

    # Проверяем, не последний ли это сет
    if len(meta['sets']) <= 1:
        return jsonify({'errors': ['Нельзя удалить единственный сет.']})

    # Стираем файлы, принадлежащие сету
    shutil.rmtree(tour.footage.in_files('frames', str(set_id)), ignore_errors=True)

    # Удаляем сет из meta['sets']
    meta['sets'].pop(str(set_id), None)

    flag_modified(tour.footage, 'meta')

    return jsonify({'id': set_id, 'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/frames/complete/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_frames_complete(tour_id, user_id=None):
    """Хэндлер конца загрузки фреймов."""
    tour = Tour.query.get_or_404(tour_id)
    token = request.args.get('token')
    set_id = request.form.get('set_id', type=int)
    target_set = find_set(tour, set_id)
    warnings = []

    # Переносим все файлы из FLOW_TMP/token/ в Footage.files/frames/{set_id}
    for item in os.scandir(os.path.join(current_app.config.get('FLOW_UPLOAD_TMP_DIR', '/tmp'), token)):
        # Угадываем ID из имени файла
        r = re.search(r'(\d+)\.([^.]+)$', item.name, re.IGNORECASE)
        if not r:
            warnings.append('Не удалось распознать, к какому фрейму относится файл {}'.format(item.name))
            continue

        frame_id = str(int(r.group(1)))
        ext = r.group(2).lower()
        tgt_fname = '{}.{}'.format(frame_id, ext)

        # Двигаем файл с исходником
        shutil.move(item.path, tour.footage.in_files('frames', str(set_id), tgt_fname))

        # Создаём фрейм в метаданных
        target_set['frames'][frame_id] = {
            'filename': tgt_fname
        }
        if frame_id in target_set.get('coords', {}):
            target_set['frames'][frame_id].update(target_set['coords'][frame_id])

    flag_modified(tour.footage, 'meta')

    set_ = target_set.copy()
    for frame_id, frame in set_['frames'].items():
        frame['url'] = '{}/frames/{}/{}'.format(tour.footage.files.url, set_id, frame['filename'])

    return jsonify({'set': set_, 'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/frames/delete/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_frame_delete(tour_id, user_id=None):
    """Удалить фрейм."""
    tour = Tour.query.get_or_404(tour_id)
    set_id = request.form.get('set_id')
    target_set = find_set(tour, set_id)
    frame_id = request.form.get('frame_id')

    if frame_id not in target_set['frames']:
        return jsonify({'errors': ['Кажется, этот кадр уже удалили. Обновите страницу.']})

    unlink_calm(tour.footage.in_files('frames', set_id, target_set['frames'][frame_id].get('filename')),
                fail_flash=True)
    del target_set['frames'][frame_id]

    flag_modified(tour.footage, 'meta')

    set_ = target_set.copy()
    for frame_id, frame in set_['frames'].items():
        frame['url'] = '{}/frames/{}/{}'.format(tour.footage.files.url, set_id, frame['filename'])

    return jsonify({'set': set_, 'problems': check_tour(tour)})


@mod.route("/users/<int:user_id>/tours/create/outside/<int:tour_id>/build/", methods=('POST',))
@roles_required('tours')
def tour_create_outside_build(tour_id, user_id=None):
    """Собирается outside тур"""
    tour = Tour.query.get_or_404(tour_id)
    log_builder = logging.getLogger('builder')
    footage = tour.footage
    meta = footage.meta

    if footage.status != 'loading':
        log_builder.error(f"Тур id={tour.id} имеет статус {tour.footage.status}, а не loading")
        flash(f"Тур id={tour.id} имеет статус {tour.footage.status}, а не loading", 'danger')

    elif footage.type != 'outside':
        log_builder.error(f'Тур id={tour.id} не является outside-туром, а имеет тип {tour.footage.type}')
        flash(f'Тур id={tour.id} не является outside-туром, а имеет тип {tour.footage.type}', 'danger')

    elif meta.get('problems'):
        log_builder.error(
            f"Тур id={tour.id} имеет нерешённые проблемы ({len(meta['problems'])} шт), поэтому его собрать нельзя")
        flash(f"Тур id={tour.id} имеет нерешённые проблемы ({len(meta['problems'])} шт), поэтому его собрать нельзя", 'danger')
    else:
        job = queue.enqueue('visual.jobs.admin.build_outside_tour',
                            tour.id,
                            result_ttl=current_app.config.get('REDIS_EXPIRE_TIME'),
                            description=f'create_outside_build: {tour.id}',
                            job_id=f'create_outside_build: {tour.id}',
                            job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'],
                            )

        flash(f'Тур «{tour.title}» собирается. Обновляйте страницу, чтобы следить за прогрессом.', 'success')
        if job is None:
            flash('Тур «{}» не собран. Обратитесь к админам'.format(tour.title), 'success')
    return redirect(url_for('.tours', user_id=user_id))
