import re
import os
import shutil
import threading

from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from sqlalchemy.orm.attributes import flag_modified
from PIL import Image

from visual.core import db
from visual.models import Footage
from visual.util import unlink_calm, downsize_img
from .forms import SkyboxForm
from .. import mod, roles_required


@mod.route('/footages/<int:footage_id>/skyboxes/')
def footage_skyboxes(footage_id):
    footage = Footage.query.options(db.joinedload('tours')).get_or_404(footage_id)
    skyboxes = {int(k): v for k, v in footage.meta.get('skyboxes', {}).items()}
    return render_template('admin/footages/skyboxes.html', footage=footage, skyboxes=skyboxes)


@mod.route('/footages/<int:footage_id>/skyboxes/edit/', methods=('GET', 'POST',))
@roles_required('tours')
def footage_skybox_edit(footage_id):
    footage = Footage.query.options(db.joinedload('tours')).get_or_404(footage_id)

    _back = url_for('.footage_skyboxes', footage_id=footage.id)

    # Проверить, что есть хоть одно разрешение
    if not footage.meta.get('resolutions'):
        flash('Сначала определите разрешения в туре.', 'danger')
        return redirect(_back)

    footage.meta.setdefault('skyboxes', {})
    skybox_id = int(request.values.get('skybox_id', max([int(x) for x in footage.meta['skyboxes'].keys()], default=0) + 1))
    skybox = footage.meta['skyboxes'].get(str(skybox_id), {})

    form = SkyboxForm(obj=skybox)

    try:
        if request.method == 'POST':
            if request.values.get('skybox_id'):
                if str(skybox_id) not in footage.meta['skyboxes']:
                    flash('Панорама не найдена', 'danger')
                    return redirect(_back)
            else:
                skybox_id = max([int(x) for x in footage.meta['skyboxes'].keys()], default=0) + 1
                skybox = {}
                footage.meta['skyboxes'][str(skybox_id)] = skybox

            if 'pos' in request.form:
                skybox['pos'] = [float(x) for x in request.form['pos'].split(',')]
            if 'q' in request.form:
                skybox['q'] = [float(x) for x in request.form['q'].split(',')]
            if 'floor' in request.form:
                skybox['floor'] = int(request.form['floor'])
            if 'disabled' in request.form:
                skybox['disabled'] = True
            elif 'disabled' in skybox:
                del skybox['disabled']

            # Проверяем и режем панораму
            if request.files.get('panorama'):
                skybox['revision'] = skybox.get('revision', 0) + 1
                footage.wurst_schneider(request.files['panorama'], skybox_id, request.form.get('render_type'),
                                        eye=None,
                                        double=False,
                                        jpeg_quality=int(request.form.get('jpeg_quality')))

            if request.files.get('panorama_binocular'):
                skybox['revision'] = skybox.get('revision', 0) + 1
                for position in ('left', 'right'):
                    footage.wurst_schneider(request.files['panorama_binocular'],
                                            skybox_id,
                                            request.form.get('render_type'),
                                            eye=position,
                                            double=True,
                                            jpeg_quality=int(request.form.get('jpeg_quality')))

            flag_modified(footage, 'meta')
            db.session.commit()
            if not request.values.get('skybox_id'):
                flash('Добавлена панорама. Не забудьте пересчитать граф достижимости!', 'info')
            return redirect(_back)
    except OSError:
        flash(flash('Не удалось открыть панораму.', 'danger'), 'danger')
    except ValueError as e:
        flash('Сэр, мне кажется, вы ввели какую-то херню в одном из полей: %s' % str(e), 'danger')

    return render_template('admin/footages/skybox_edit.html', footage=footage, skybox_id=skybox_id, skybox=skybox, form=form)


@mod.route('/footages/<int:footage_id>/skybox/delete/', methods=('POST', ))
@roles_required('tours')
def footage_skybox_delete(footage_id):
    footage = Footage.query.get_or_404(footage_id)

    _back = redirect(url_for('.footage_skyboxes', footage_id=footage.id))

    skybox_id = request.form.get('skybox_id', type=int)
    if str(skybox_id) not in footage.meta.get('skyboxes', {}):
        flash('Панорама не найдена.', 'danger')
        return _back

    # Удаляем файлы
    for res in footage.meta.get('resolutions', []):
        for face in range(6):
            unlink_calm(footage.in_files(str(res), '%d-%d.jpg' % (skybox_id, face)), fail_flash=True)

    # Чистим туры
    for tour in footage.tours:
        if str(skybox_id) in tour.meta.get('skyboxes', {}):
            del tour.meta['skyboxes'][str(skybox_id)]
            flag_modified(tour, 'meta')
        if tour.meta.get('start', {}).get('skybox') == skybox_id:
            tour.meta.pop('start', None)
            flag_modified(tour, 'meta')

    del footage.meta['skyboxes'][str(skybox_id)]

    # Удаляем skybox из passways
    if 'passways' in footage.meta:
        new_passways = []
        for point in tour.footage.meta['passways']:
            if str(skybox_id) not in point:
                new_passways.append(point)
        footage.meta['passways'] = new_passways

    flag_modified(footage, 'meta')
    db.session.commit()

    flash('Панорама %d удалена' % skybox_id, 'success')

    return _back


def get_res(footage, src):
    try:
        res = int(src)
        if not res:
            raise ValueError
    except ValueError:
        flash('Введите разрешение панорам.', 'danger')
        return False

    if res in footage.meta.get('resolutions', []):
        flash('Такое разрешение уже есть', 'danger')
        return False

    if footage.max_res and res > footage.max_res and footage.meta.get('skyboxes'):
        flash('Когда уже есть загруженные панорамы, нельзя создать разрешение, выше максимального.', 'danger')
        return False

    return res


def resize_skyboxes(footage, dst_res, delete_res=None):
    """Запускает тред, который добавляет разрешение dst_res в meta['resolutions'] и
    создаёт панорамы данного разрешения из панорам с максимальным разрешением. Если указано
    delete_res, то удаляет это разрешение и директорию с этими панорамами.
    """
    footage.meta.setdefault('_bg_jobs', {})['resize'] = True

    flag_modified(footage, 'meta')
    db.session.commit()

    def resize(id, dst_res, delete_res, context):
        with context:
            footage = Footage.query.get(id)
            os.makedirs(footage.in_files(str(dst_res)), mode=0o755, exist_ok=True)

            # Если были заданы разрешения раньше, то ресайзим предыдущие панорамы
            if footage.meta.get('resolutions'):
                for skybox in os.listdir(footage.in_files(str(footage.max_res))):
                    downsize_img(
                        footage.in_files(str(footage.max_res), skybox),
                        footage.in_files(str(dst_res), skybox),
                        (dst_res, dst_res)
                    )

            footage.meta.setdefault('resolutions', []).append(dst_res)
            if delete_res:
                footage.meta['resolutions'].remove(delete_res)
                shutil.rmtree(footage.in_files(str(delete_res)), ignore_errors=True)

            footage.meta['resolutions'].sort()

            if footage.meta.get('_bg_jobs', {}).get('resize'):
                del footage.meta['_bg_jobs']['resize']

            flag_modified(footage, 'meta')
            db.session.commit()

    thread = threading.Thread(target=resize, args=(footage.id, dst_res, delete_res, current_app.app_context()))
    thread.start()


@mod.route('/footages/<int:footage_id>/res_add/', methods=('POST', ))
@roles_required('tours')
def footage_res_add(footage_id):
    footage = Footage.query.get_or_404(footage_id)

    res = get_res(footage, request.form.get('res'))

    if res:
        resize_skyboxes(footage, res)

    return redirect(url_for('.footage_skyboxes', footage_id=footage.id))


@mod.route('/footages/<int:footage_id>/res_edit/', methods=('POST', ))
@roles_required('tours')
def footage_res_edit(footage_id):
    footage = Footage.query.get_or_404(footage_id)

    old_res = int(request.form.get('old_res'))
    new_res = get_res(footage, request.form.get('new_res'))

    if new_res and old_res in footage.meta.get('resolutions') and new_res != old_res:
        flash('Панорамы в разрешении %dpx пересчитываются в %dpx.' % (old_res, new_res), 'success')
        resize_skyboxes(footage, new_res, delete_res=old_res)

    return redirect(url_for('.footage_skyboxes', footage_id=footage.id))


@mod.route('/footages/<int:footage_id>/res_delete/', methods=('POST', ))
@roles_required('tours')
def footage_res_delete(footage_id):
    footage = Footage.query.get_or_404(footage_id)

    res = int(request.form.get('res'))
    if res not in footage.meta.get('resolutions', []):
        flash('Разрешение %r не найдено' % res, 'danger')
    else:
        shutil.rmtree(os.path.join(footage.files.abs_path, str(res)), ignore_errors=True)
        footage.meta['resolutions'] = [resolution for resolution in footage.meta['resolutions'] if resolution != res]
        flag_modified(footage, 'meta')
        db.session.commit()
        flash('Разрешение %d удалено' % res, 'success')

    return redirect(url_for('.footage_skyboxes', footage_id=footage.id))


@mod.route('/footages/<int:footage_id>/skyboxs/upload/', methods=('POST', ))
@roles_required('tours')
def footage_skyboxs_upload(footage_id):
    errors = []
    messages = []

    def save_skyboxs(input_type):

        for image in request.files.getlist(input_type):

            if image.filename == '':
                continue

            skybox_id_group = re.search('(\d+)\.[jpg|png|jpeg]', image.filename.lower())
            if skybox_id_group is None:
                errors.append('Название панорамы "{}" не совпадает с шаблоном ("1.RGB_color.1.jpg")'.format(image.filename))
                continue

            skybox_id = int(skybox_id_group.group(1))

            if 'skyboxes' not in footage.meta or str(skybox_id) not in footage.meta['skyboxes']:
                errors.append('Панорама "{}" не найдена.'.format(image.filename))
                continue
            try:
                if 'binocular' not in input_type:
                    footage.wurst_schneider(image, skybox_id, render_type,
                                            eye=None, double=False, jpeg_quality=jpeg_quality)
                    input_type_title = 'Основная'
                else:
                    footage.wurst_schneider(image, skybox_id, render_type,
                                            eye='left', double=True, jpeg_quality=jpeg_quality)
                    footage.wurst_schneider(image, skybox_id, render_type,
                                            eye='right', double=True, jpeg_quality=jpeg_quality)
                    input_type_title = 'Бинокулярная'
            except OSError:
                errors.append('Не удалось открыть панораму "{}".'.format(image.filename))
                continue
            except:
                continue

            skybox = footage.meta['skyboxes'][str(skybox_id)]
            skybox['revision'] = skybox.get('revision', 0) + 1

            messages.append('{} панорама "{}" успешно заменена.'.format(input_type_title,
                                                                        image.filename))

    render_type = request.form.get('render_type')
    jpeg_quality = int(request.form.get('jpeg_quality'))
    footage = Footage.query.get_or_404(footage_id)

    if render_type not in ['vray', 'corona']:
        errors.append('Указан неверный тип рендера.')
    elif jpeg_quality not in range(10, 101):
        errors.append('JPEG сжатие вне диапазона.')
    else:
        save_skyboxs('skyboxs')
        save_skyboxs('skyboxs_binocular')

        if 'testing' in request.form:
            footage.status = 'testing'

        flag_modified(footage, 'meta')
        db.session.commit()

    if errors:
        return jsonify({'errors': errors})
    return jsonify({'status': 'ok', 'messages': messages})


@mod.route('/footages/<int:footage_id>/skyboxs/binocular/upload/', methods=('POST', ))
@roles_required('tours')
def footage_skyboxes_binocular_upload(footage_id):

    def validate_binocular_skyboxes(footage):
        count_skyboxes = len(footage.meta.get('skyboxes', {}))
        skybox_path = footage.in_files(str(footage.max_res), 'left')
        if os.path.exists(skybox_path) and count_skyboxes * 6 == len(os.listdir(skybox_path)):
            return True
        return False

    def delete_binocular_skyboxes(footage):
        for resolution in footage.meta.get('resolutions', []):
            for type in ('left', 'right'):
                shutil.rmtree(footage.in_files(str(resolution), type), ignore_errors=True)

    errors = []
    footage = Footage.query.get_or_404(footage_id)

    if request.form.get('action') == 'save':
        if validate_binocular_skyboxes(footage):
            footage.meta['binocular'] = True
            if 'testing' in request.form:
                footage.status = 'testing'
            flag_modified(footage, 'meta')
        else:
            errors.append('Количество загруженных панорам не совпадает с количеством точек.')
            delete_binocular_skyboxes(footage)
    elif request.form.get('action') == 'upload':
        render_type = request.form.get('render_type')
        jpeg_quality = int(request.form.get('jpeg_quality'))

        if render_type not in ['vray', 'corona']:
            errors.append('Указан неверный тип рендера.')
        elif jpeg_quality not in range(10, 101):
            errors.append('JPEG сжатие вне диапазона.')
        else:
            for image in request.files.getlist('skyboxs_binocular'):
                skybox_id_group = re.search('(\d+)\.[jpg|png|jpeg]', image.filename.lower())
                if skybox_id_group is None:
                    errors.append('Название панорамы "{}" не совпадает с шаблоном ("1.RGB_color.1.jpg")'.format(image.filename))
                    continue

                skybox_id = int(skybox_id_group.group(1))

                if 'skyboxes' not in footage.meta or str(skybox_id) not in footage.meta['skyboxes']:
                    errors.append('Панорама "{}" не найдена.'.format(image.filename))
                    continue
                try:
                    footage.wurst_schneider(image, skybox_id, render_type,
                                            eye='left', double=True, jpeg_quality=jpeg_quality)
                    footage.wurst_schneider(image, skybox_id, render_type,
                                            eye='right', double=True, jpeg_quality=jpeg_quality)
                except OSError:
                    errors.append('Не удалось открыть панораму "{}".'.format(image.filename))
                    continue
    if errors:
        return jsonify({'errors': errors})

    flag_modified(footage, 'meta')
    db.session.commit()
    return jsonify({'status': 'ok', 'messages': 'Съёмка стала бинокулярной'})


@mod.route('/footages/<int:footage_id>/skyboxs/binocular/delete/', methods=('POST', ))
@roles_required('tours')
def footage_skyboxes_binocular_delete(footage_id):
    footage = Footage.query.get_or_404(footage_id)
    if 'binocular' in footage.meta:
        del footage.meta['binocular']
    for resolution in footage.meta.get('resolutions', []):
        panorams_dir = footage.in_files(str(resolution))
        shutil.rmtree(os.path.join(panorams_dir, 'left'), ignore_errors=True)
        shutil.rmtree(os.path.join(panorams_dir, 'right'), ignore_errors=True)
    for skybox in footage.meta['skyboxes'].values():
        for size in skybox.get('files_size', {}).values():
            if 'left' in size:
                del size['left']
            if 'right' in size:
                del size['right']
    flag_modified(footage, 'meta')
    db.session.commit()
    flash('Съёмка стала не бинокулярной', 'success')
    return redirect(request.referrer if request.referrer else url_for('.footage_skyboxes', footage_id=footage_id))
