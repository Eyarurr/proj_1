from datetime import datetime
import os

from flask import render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db, queue_quick
from visual.models import Footage
from visual.bgjobs import BgJobState
from visual.util import ModelInfo
from .. import mod, roles_required


def get_model_dir(footage, models_dirname='models'):
    """Возвращает сортированный по имени список с файлами в директории tour.in_files(models_dirname)
    {'name': имя, 'stat': os.stat}
    """
    model_dir = []

    for filename in os.listdir(footage.in_files(models_dirname)):
        entry = {
            'name': filename,
            'stat': os.stat(os.path.join(footage.files.abs_path, models_dirname, filename))
        }
        if entry['stat'].st_mode & 0x4000:
            entry['is_dir'] = True
        model_dir.append(entry)

    model_dir.sort(key=lambda x: x['name'].lower())

    return model_dir


@mod.route('/footages/<int:footage_id>/model/')
def footage_model(footage_id):
    footage = Footage.query.options(db.joinedload('tours')).get_or_404(footage_id)
    if footage.type not in ('real', 'virtual') or footage.status not in ('testing', 'published', 'banned'):
        abort(403, 'Эта страница работает с турами типов "vrtual" и "real" в статусах "testing", "published", "banned"')

    models_dirname = 'models'

    if footage.files:
        os.makedirs(footage.in_files(models_dirname), mode=0o755, exist_ok=True)
    model_dir = get_model_dir(footage)

    bgstate = BgJobState.load('passways', footage.id)

    return render_template('admin/footages/model.html', footage=footage,
                           models_dirname=models_dirname, model_dir=model_dir,
                           bgstate=bgstate)


@mod.route('/footages/<int:footage_id>/model/info/')
def footage_model_info(footage_id):
    """Рендерит HTML со статистикой по модели из utils.ModelInfo. Имя модели в GET['filename']"""
    footage = Footage.query.options(db.joinedload('tours')).get_or_404(footage_id)

    try:
        model_info = ModelInfo()
        model_info.scan_file(footage.in_files('models', request.args.get('filename')))
    except Exception as e:
        return "Не удалось изучить модель, возможно она битая.<br><br><pre>" + str(e) + "</pre>"

    mtime = datetime.fromtimestamp(model_info.filestat.st_mtime)

    return render_template('admin/footages/model_info.html', mi=model_info, mtime=mtime)


@mod.route('/footages/<int:footage_id>/model/delete-file/', methods=('POST', ))
@roles_required('tours')
def footage_model_delete_file(footage_id):
    footage = Footage.query.get(footage_id)

    filename = request.form.get('filename')
    os.unlink(os.path.join(footage.files.abs_path, 'models', filename))

    # Если файл использовался в метаданных, то удаляем его оттуда и стираем passways
    for k in ('model', 'mtl'):
        if footage.meta.get(k) == 'models/' + filename:
            del footage.meta[k]
            footage.meta.pop('passways', None)
            flag_modified(footage, 'meta')

    db.session.commit()

    flash('Файл {} удалён.'.format(filename), 'success')

    return redirect(url_for('.footage_model', footage_id=footage.id))


@mod.route('/footages/<int:footage_id>/model/upload/', methods=('POST', ))
@roles_required('tours')
def footage_model_upload(footage_id):
    footage = Footage.query.get(footage_id)

    for file in request.files.getlist('files'):
        dst = os.path.join(footage.files.abs_path, 'models', file.filename)
        if os.path.isfile(dst):
            flash('Файл {} не загружен, такой уже есть.'.format(file.filename), 'warning')
        elif os.path.isdir(dst):
            flash('Файл не загружен, добавьте файл.', 'warning')
        else:
            model_revision = footage.meta.get('model_revision', 0) + 1
            footage.meta['model_revision'] = model_revision
            if '_loading' in footage.meta:
                footage.meta['_loading']['model_revision'] = model_revision
            flag_modified(footage, 'meta')
            db.session.commit()
            file.save(dst)

    return redirect(url_for('.footage_model', footage_id=footage.id))


@mod.route('/footages/<int:footage_id>/model/use/', methods=('POST', ))
@roles_required('tours')
def footage_model_use(footage_id):
    footage = Footage.query.get(footage_id)

    back = url_for('.footage_model', footage_id=footage.id)

    filename = request.form.get('filename')

    if filename.lower().endswith('.obj'):
        footage.meta['model'] = 'models/' + filename
        footage.meta['model_size_gz'], footage.meta['model_size'] = footage.get_gz_size()
        footage.meta.pop('passways', None)
        flag_modified(footage, 'meta')
        db.session.commit()

        job = queue_quick.enqueue('visual.jobs.admin.calc_passways',
                                  footage.id, compare=None, no_recalc=None,
                                  result_ttl=current_app.config.get('REDIS_EXPIRE_TIME'),
                                  description=f'calc_passways: {footage.id}',
                                  job_id=f'calc_passways: footage-{footage.id}',
                                  job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'],
                                  )
        if job is None:
            # Задача не создалась
            flash('Не удалось создать задачу на упаковку тура, что-то с очередями. Дёрните админов.', 'danger')

        flash('Модель обрабатывается. Обновляйте страницу, чтобы следить за прогрессом', 'success')

    elif filename.lower().endswith('.mtl'):
        footage.meta['mtl'] = 'models/' + filename
        flag_modified(footage, 'meta')
        db.session.commit()

    else:
        flash('Непонятно, как использовать этот файл. Его имя не заканчивается на .mtl или .obj', 'danger')
        return redirect(back)

    return redirect(back)


@mod.route('/footages/<int:footage_id>/passways/recalc/', methods=('POST', ))
@roles_required('tours')
def footage_passways_recalc(footage_id):
    footage = Footage.query.get(footage_id)
    if request.form.get('calc_size'):
        footage.meta['model_size_gz'], footage.meta['model_size'] = footage.get_gz_size()
        flag_modified(footage, 'meta')
        db.session.commit()
    compare = request.form.get('compare', None)
    no_recalc = request.form.get('no_recalc', None)
    job = queue_quick.enqueue('visual.jobs.admin.calc_passways',
                              footage.id, compare, no_recalc,
                              result_ttl=current_app.config.get('REDIS_EXPIRE_TIME'),
                              description=f'calc_passways: {footage.id}',
                              job_id=f'calc_passways: footage-{footage.id}',
                              job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'],
                              )
    flash(f'Модель обрабатывается. Обновляйте страницу, чтобы следить за прогрессом.', 'success')

    if job is None:
        # Задача не создалась
        flash('Не удалось создать задачу на упаковку тура, что-то с очередями. Дёрните админов.', 'danger')

    return redirect(url_for('.footage_model', footage_id=footage.id))
