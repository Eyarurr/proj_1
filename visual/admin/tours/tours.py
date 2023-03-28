import os
import shutil
import json
import uuid
from datetime import datetime, timedelta
import traceback

from PIL import Image
from flask import render_template, request, redirect, url_for, flash, send_file, jsonify, current_app, \
    render_template_string, abort
from flask_login import current_user
from lagring import AssetProcessingException, AssetRequirementsException
from sqlalchemy import Integer, String, func
from sqlalchemy.orm.attributes import flag_modified
import rq

from visual.core import db, queue, queue_quick
from visual.util import flash_errors, unzip_footage_tour
from visual.models import User, Footage, Tour, Folder, Offer, OfferTour, AggregateCount, TourFeature, TourPaidFeature, \
    ToursChangedJurisdiction
from .. import mod, roles_required
from .forms import ToursFilter, TourForm, TourUploadForm, ToursMovedFilter


@mod.route('/tours/')
@mod.route('/users/<int:user_id>/tours/')
@mod.route('/footages/<int:footage_id>/tours/')
def tours(user_id=None, footage_id=None):
    filters = ToursFilter(request.args)
    if footage_id:
        footage = Footage.query.get_or_404(footage_id)
    else:
        footage = None

    # Поиск по папкам
    if filters.search.data and filters.search.data.startswith('/') and len(filters.search.data) > 1:
        search = filters.search.data[1:]
        folders = Folder.query.filter(Folder.title.ilike('%' + search + '%')).all()
        if len(folders) == 1:
            return redirect(url_for('.tours', user_id=folders[0].user_id, folder_id=folders[0].id))
        return render_template('admin/tours/foldersearch.html', folders=folders, search=search, filters=filters)

    current_folder = None
    if user_id:
        user = User.query.get_or_404(user_id)

        # Считаем количество туров в корне
        cnt_root_tours = db.session.query(db.func.count(Tour.id)).filter(Tour.user_id == user.id,
                                                                         Tour.folder_id == None).scalar()
        filters.folder_id.choices[1] = ('0', 'Корень ({})'.format(cnt_root_tours))

        # Строим список папок юзера с количеством туров в них
        q = db.session.query(Folder, db.func.count(Tour.id)) \
            .outerjoin(Tour) \
            .filter(Folder.user_id == user.id) \
            .group_by(Folder.id) \
            .order_by(Folder.title)
        for folder, cnt_tours in q.all():
            filters.folder_id.choices.append([folder.id, '{} ({})'.format(folder.title, cnt_tours)])
            if str(folder.id) == filters.folder_id.data:
                current_folder = folder
    else:
        user = None

    # Основной запрос
    q = db.session.query(Tour) \
        .join(User, User.id == Tour.user_id) \
        .join(Footage, Footage.id == Tour.footage_id) \
        .outerjoin(Folder, Folder.id == Tour.folder_id) \
        .options(db.joinedload(Tour.user), db.contains_eager(Tour.footage), db.joinedload(Tour.folder))

    if footage:
        q = q.filter(Tour.footage_id == footage.id)

    if user:
        q = q.filter(Tour.user_id == user.id)
        if filters.folder_id.data == '0':
            q = q.filter(Tour.folder_id == None)
        elif filters.folder_id.data != '':
            q = q.filter(Tour.folder_id == filters.folder_id.data)

    if filters.type.data:
        q = q.filter(Footage.type == filters.type.data)

    if filters.status.data:
        q = q.filter(Footage.status == filters.status.data)

    # Фильтр по фиче
    if filters.feature.data:
        q = q.join(TourFeature).filter(TourFeature.feature == filters.feature.data).options(db.contains_eager(Tour.features))
        if filters.feature.data == 'branding':
            q = q.join(TourPaidFeature).filter(TourPaidFeature.feature == filters.feature.data)

    if filters.search.data:
        if filters.search.data.startswith('#') or filters.search.data.startswith('№'):
            return redirect(url_for('.tour_edit', tour_id=int(filters.search.data[1:].strip())))
        like = '%' + filters.search.data.lower() + '%'
        q = q.filter(db.func.lower(Tour.title).like(like))

    # Сортировка
    if filters.sort.data == 'title':
        q = q.order_by(Tour.title, Tour.created.desc(), Tour.id.desc())
    elif filters.sort.data == 'folder':
        if user:
            q = q.order_by(Folder.title.nullsfirst(), Tour.title, Tour.created.desc(), Tour.id.desc())
        else:
            q = q.order_by(User.name, Folder.title.nullsfirst(), Tour.title, Tour.created.desc(), Tour.id.desc())
    else:
        q = q.order_by(Tour.created.desc(), Tour.id.desc())

    tours = q.paginate(per_page=50, error_out=False)

    # Для объектов в статусе queued и processing собираем job'ы из очереди, чтобы показывать, что там происходит
    jobs = {}
    for tour in tours.items:
        if tour.footage.status in ('queued', 'processing'):
            job_id = tour.footage.meta.get('_' + tour.footage.status, {}).get('job_id')
            if not job_id:
                continue
            try:
                job = queue.fetch_job(job_id)
                if job:
                    jobs[tour.id] = job
            except rq.exceptions.NoSuchJobError:
                pass
            except Exception as e:
                flash('Были проблемы при получении queue job для тура {}: {}'.format(tour.id, str(e)), 'warning')

    # @todo: tour.features и tour.paid_features_rel будут всегда лениво загружаться при генерации шаблона, что сделает 50 лишних,
    # @todo: хоть и лёгких, запросов к базе; Хорошо бы из тут загрузить для всех полученных туров и распихать а tour.features

    return render_template('admin/tours/index.html', tours=tours, filters=filters,
                           user_id=user_id, user=user, folder=current_folder,
                           footage_id=footage_id, footage=footage,
                           jobs=jobs)


@mod.route('/tours_moved/')
def tours_moved():
    search = ToursMovedFilter(request.args)
    q = db.session.query(ToursChangedJurisdiction)
    if request.args.get('search_by') == 'local_id':
        try:
            r = int(search.search_field.data)
            q = q.filter(ToursChangedJurisdiction.local_id == search.search_field.data)
        except:
            flash('Должно быть число', 'danger')

    if request.args.get('search_by') == 'remote_id':
        try:
            r = int(search.search_field.data)
            q = q.filter(ToursChangedJurisdiction.remote_id == search.search_field.data)
        except:
            flash('Должно быть число', 'danger')

    if request.args.get('search_by') == 'server':
        try:
            r = str(search.search_field.data)
            q = q.filter(ToursChangedJurisdiction.moved_to == search.search_field.data)
        except:
            flash('Должна быть строка', 'danger')

    if request.args.get('search_by') == 'created':
        try:
            start = datetime.strptime(search.search_field.data, '%d.%m.%Y')
            finish = start + timedelta(hours=24)
            q = q.filter(db.and_(ToursChangedJurisdiction.created >= start, ToursChangedJurisdiction.created <= finish))
        except:
            flash('Неверный формат даты', 'danger')
    tours = q.paginate(per_page=50, error_out=False)
    return render_template('admin/tours/tours_moved.html', tours=tours, form=search)


@mod.route('/tours/<int:tour_id>/download/')
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/download/')
def tour_download(tour_id, user_id=None):
    """Ставит в очередь queue_quick архивирование тура."""
    tour = Tour.query.get_or_404(tour_id)

    job = queue_quick.enqueue('visual.jobs.admin.zip_tour', tour.id, current_user.id,
                              job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'])
    if job is None:
        # Задача уже успела завершиться (скорее всего, какой-то хуйнёй)
        flash('Не удалось создать задачу на упаковку тура, что-то с очередями. Дёрните админов.', 'danger')
    else:
        flash('Тур упаковывается в ZIP. Когда он будет готов, вам на почту {} придёт ссылка на его скачивание.'.format(
            current_user.email), 'success')

    return redirect(url_for('.tour_edit', tour_id=tour.id, user_id=user_id))


@mod.route('/users/<int:user_id>/tours/upload-zip/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_upload(user_id):
    """Создаёт съёмку и тур из архива. Формат архива — тот же, что отдаёт admin.tour_download.
    """
    user = User.query.get_or_404(user_id)
    form = TourUploadForm()
    form.folder_id.choices = [('0', 'Корень')] + [(str(f.id), f.title) for f in user.folders]
    if request.args.get('folder_id'):
        form.folder_id.default = request.args['folder_id']
        form.process()

    if form.validate_on_submit():
        job = queue_quick.enqueue(
            'visual.jobs.admin.unzip_tours', current_user.id, request.form,
            job_timeout=current_app.config['BUILDER_JOB_TIMEOUT']
        )
        if job is None:
            # Задача уже успела завершиться (скорее всего, какой-то хуйнёй)
            flash('Не удалось создать задачу на распаковку туров, что-то с очередями. Дёрните админов.', 'danger')
        else:
            flash('Туры распаковываются. Когда они будут готовы, вам на почту {} придёт уведомление.'.format(
                current_user.email),
                'success')

        return redirect(url_for('.tours', user_id=user_id))

    flash_errors(form)

    return render_template('admin/tours/upload.html', form=form, user_id=user_id,
                           flow_token='admin-upload-zip-{}'.format(uuid.uuid4()))


@mod.route('/tours/<int:tour_id>/edit/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/edit/', methods=('GET', 'POST'))
@mod.route('/footages/<int:footage_id>/tours/new/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_edit(tour_id=None, user_id=None, footage_id=None):
    if tour_id is None and footage_id is not None:
        footage = Footage.query.get_or_404(footage_id)
        user = footage.user
        tour = Tour(
            footage=footage,
            user=footage.user,
            footage_id=footage.id,
            user_id=footage.user_id,
            created_by=current_user.id,
            meta={}
        )
        usage = []
    else:
        tour = Tour.query.get_or_404(tour_id)
        user = tour.user

        # Где используется тур?
        usage = Offer.query.join(OfferTour).filter(OfferTour.tour_id == tour.id).all()

    form = TourForm(obj=tour)
    form.footage_status.choices = list(Footage.STATUSES.items())
    form.folder_id.choices = [('', 'Корень')] + [(str(f.id), f.title) for f in user.folders]

    if form.validate_on_submit():
        if form.gallery_admin.data == 'None':
            form.gallery_admin.data = None
        else:
            gallery_sort = (db.session.query(db.func.max(Tour.gallery_sort)).filter(
                Tour.gallery_admin != 0).scalar() or 0) + 1
            tour.gallery_sort = gallery_sort

        if form.folder_id.data == '':
            form.folder_id.data = None

        if form.password_clear.data:
            tour.password_hash = None
        elif form.password.data != '':
            tour.password_hash = Tour.hash_password(form.password.data)

        if tour_id is None:
            db.session.flush()
            db.session.add(tour)
            db.session.flush()

        try:
            if form.screen.data:
                tour.preview = form.screen.data
            tour.footage.status = form.footage_status.data
            form.populate_obj(tour)
        except AssetProcessingException:
            flash('Не удалось обработать обложку. Убедитесь, что это JPEG или PNG.', 'danger')
        except AssetRequirementsException:
            flash('Обложка слишком маленькая.', 'danger')
        else:
            tour.save_features()
            db.session.commit()

            if request.form.get('redirect'):
                url = url_for(request.form['redirect'], tour_id=tour.id, user_id=user_id)
            else:
                url = url_for('.tours', user_id=user_id)
            return redirect(url)

    else:
        flash_errors(form)
        form.footage_status.data = tour.footage.status

    return render_template('admin/tours/edit.html', tour=tour, form=form, Tour=Tour, usage=usage, footage_id=footage_id,
                           user_id=user_id)


@mod.route('/tours/<int:tour_id>/delete/', methods=('POST',))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/delete/', methods=('POST',))
@roles_required('tours')
def tour_delete(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    tour.delete()
    db.session.commit()
    flash('Тур «%s» удалён навсегда.' % tour.title, 'success')

    return redirect(url_for('.tours', user_id=user_id))


@mod.route('/tours/<int:tour_id>/move/', methods=('POST',))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/move/', methods=('POST',))
@roles_required('tours')
def tour_move(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    new_user_id = request.form.get('user_id')
    new_folder_id = request.form.get('folder_id')
    if not new_folder_id:
        new_folder_id = None

    tour.user_id = new_user_id
    tour.folder_id = new_folder_id
    db.session.commit()

    if tour.folder_id:
        flash('Тур «{}» перенесен пользователю {} в папку «{}».'.format(tour.title, tour.user.name, tour.folder.title),
              'success')
    else:
        flash('Тур «{}» перенесен пользователю {} в корневую папку.'.format(tour.title, tour.user.name), 'success')

    # Если урл был с user_id, то переходим в редактор тура с новым user_id в URL
    if user_id:
        user_id = tour.user_id
    return redirect(url_for('.tour_edit', tour_id=tour_id, user_id=user_id))


@mod.route('/tours/<int:tour_id>/copy/', methods=('POST',))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/copy/', methods=('POST',))
@roles_required('tours')
def tour_copy(tour_id, user_id=None):
    tour = db.session.query(Tour).get_or_404(tour_id)
    folder_id = request.form.get('folder_id')
    title = request.form.get('title')
    copy_footage = request.form.get('copy_footage')
    copy_meta = request.form.get('copy_meta')
    if not title:
        title = f'Unnamed Copy-{tour.title}'
    if folder_id and folder_id != '0':
        folder = db.session.query(Folder).filter(Folder.user_id == tour.user_id, Folder.id == folder_id).first()
        if not folder:
            abort(403, 'У этого пользователя нет папки id={}.'.format(folder_id))

    job = queue_quick.enqueue('visual.jobs.admin.copy_tour',
                              tour.id, title, copy_footage, copy_meta, folder_id,
                              result_ttl=current_app.config.get('REDIS_EXPIRE_TIME'),
                              description=f'{tour_id}-{title}',
                              job_id=f'copy_tour:{tour_id}-{title}',
                              job_timeout=current_app.config['BUILDER_JOB_TIMEOUT'])

    flash('Тур копируется в фоновом режиме. Обновляйте страницу, чтобы следить за прогрессом.', 'success')

    if job is None:
        # Задача не создалась
        flash('Не удалось создать задачу на упаковку тура, что-то с очередями. Дёрните админов.', 'danger')

    return redirect(url_for('.tours', user_id=user_id))


@mod.route('/tours/<int:tour_id>/paid-features/', methods=('POST',))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/paid-features/', methods=('POST',))
@roles_required('tours')
def tour_paid_features(tour_id=None, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    for k, v in request.form.items():
        if k.startswith('paid_till.'):
            feature = k[10:]
            if v:
                try:
                    paid_till = datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    flash('Неверная дата "{}", вводите в формате YYYY-MM-DD HH:MM:SS'.format(v), 'danger')
                    return redirect(url_for('.tour_edit', tour_id=tour.id, user_id=user_id))
                TourPaidFeature.query.filter_by(tour_id=tour.id, feature=feature).update({'paid_till': paid_till})
            else:
                TourPaidFeature.query.filter_by(tour_id=tour.id, feature=feature).delete()
            continue

        if k == 'new.feature' and v != '':
            if v in tour.paid_features_time_left().keys():
                flash('У тура уже есть платная фича "{}"'.format(v), 'danger')
                return redirect(url_for('.tour_edit', tour_id=tour.id, user_id=user_id))
            try:
                paid_till = datetime.strptime(request.form['new.paid_till'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                flash('Неверная дата "{}", вводите в формате YYYY-MM-DD HH:MM:SS'.format(v), 'danger')
                return redirect(url_for('.tour_edit', tour_id=tour.id, user_id=user_id))
            pf = TourPaidFeature(tour_id=tour.id, feature=v, paid_till=paid_till)
            db.session.add(pf)

    db.session.commit()
    flash('Платные фичи сохранены.', 'success')

    return redirect(url_for('.tour_edit', tour_id=tour.id, user_id=user_id))


@mod.route('/tours/<int:tour_id>/json/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/json/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_json(tour_id=None, user_id=None):
    """
    Редактирование метаданных. Мету разберёт на свойства 1-го уровня шаблон, в ответе все эти свойства
    придут с именами "meta.{{ property_name }}
    """
    tour = Tour.query.get_or_404(tour_id)

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
            tour.meta = meta
            flag_modified(tour, 'meta')
            tour.save_features()
            db.session.commit()
            flash('Изменения сохранены', 'success')
            redirect(url_for('.tour_json', tour_id=tour.id, user_id=user_id))

    if mode == 'single':
        jsoned = json.dumps(tour.meta, indent=4, ensure_ascii=False, sort_keys=True)
    else:
        jsoned = {}
        indent = {
            'passways': None,
            'resolutions': None
        }
        for key, value in tour.meta.items():
            jsoned[key] = json.dumps(value, indent=indent.get(key, 4), ensure_ascii=False, sort_keys=True)

    return render_template('admin/tours/json.html', tour=tour, jsoned=jsoned, mode=mode, user_id=user_id)


@mod.route('/tours/<int:tour_id>/splash/', methods=('GET', 'POST'))
@mod.route('/users/<int:user_id>/tours/<int:tour_id>/splash/', methods=('GET', 'POST'))
@roles_required('tours')
def tour_splash(tour_id, user_id=None):
    tour = Tour.query.get_or_404(tour_id)

    def _bool(v):
        return v == 'True'

    def _int(v):
        return int(v)

    def _str(v):
        return str(v)

    def _rgb(v):
        rgba = v[5:-1].split(',')
        return [int(rgba[x]) for x in range(3)] + [float(rgba[3])]

    OPTIONS = {
        'bg_color': _rgb,
        'progress': _bool,
        'cancel_timeout': _int,
        'cancel_url': _str,
        'cancel_target': _str,
        'redirect': _str,
    }

    MULTILANG_PROPERTIES = ['cancel_text', 'cancel_html']

    if not tour.meta.get('splash'):
        tour.meta['splash'] = {}

    if request.method == 'POST':
        for option in MULTILANG_PROPERTIES:
            if option in tour.meta['splash']:
                del tour.meta['splash'][option]

        for k, v in request.form.items():

            if k in OPTIONS:
                if v == '':
                    if k in tour.meta['splash']:
                        del tour.meta['splash'][k]
                else:
                    tour.meta['splash'][k] = OPTIONS[k](v)
            else:

                for option in MULTILANG_PROPERTIES:
                    if option in k:
                        if v == '':
                            if k in tour.meta['splash']:
                                del tour.meta['splash'][k]
                        x = k.split('.')
                        if len(x) == 1 and v != '':
                            tour.meta['splash'][option] = v
                        elif len(x) == 2:
                            if option not in tour.meta['splash'] or type(tour.meta['splash'][option]) is not dict:
                                tour.meta['splash'][option] = {}
                            if v != '':
                                tour.meta['splash'][option][x[1]] = v

        bg_url = request.form.get('bg_url', '')
        if bg_url == 'True':
            if request.files and request.files['screen'].filename != '':
                if tour.meta['splash'].get('bg_url'):
                    os.remove(tour.in_files(tour.meta['splash']['bg_url']))
                screen_file = request.files['screen']
                os.makedirs(tour.in_files('splash'), exist_ok=True)
                tour.meta['splash']['bg_url'] = 'splash/splash.{}'.format(screen_file.filename.split('.')[-1])
                img = Image.open(screen_file)
                img.save(tour.in_files(tour.meta['splash']['bg_url']), progressive=True)
        else:
            if 'bg_url' in tour.meta['splash']:
                shutil.rmtree(tour.in_files('splash'), ignore_errors=True)
                del tour.meta['splash']['bg_url']
        if bg_url == 'False':
            tour.meta['splash']['bg_url'] = False

        if not tour.meta['splash']:
            tour.meta.pop('splash', None)

        flag_modified(tour, 'meta')
        tour.save_features()
        db.session.commit()
        flash('Настройки сохранены', 'success')
        return redirect(url_for('.tour_splash', tour_id=tour.id, user_id=user_id))

    return render_template('admin/tours/splash.html', tour=tour, user_id=user_id)


@mod.route('/tours/docs/')
def docs():
    return render_template('admin/tours/docs/index.html')


@mod.route('/users/<int:user_id>/folders/new/', methods=('POST',))
@mod.route('/users/<int:user_id>/folders/<int:folder_id>/edit/', methods=('POST',))
@roles_required('users')
def folder_edit(user_id, folder_id=None):
    user = User.query.get_or_404(user_id)
    if folder_id:
        folder = Folder.query.filter_by(id=folder_id, user_id=user.id).first_or_404()
    else:
        folder = Folder(user_id=user.id)
        db.session.add(folder)

    title = request.form.get('title', '').strip()
    if title == '':
        if folder_id:
            db.session.delete(folder)
            redirect_folder = None
        else:
            flash('Введите название папки', 'danger')
            return redirect(url_for('.tours', user_id=user_id))
    else:
        folder.title = title
        redirect_folder = folder.id

    db.session.commit()

    return redirect(url_for('.tours', user_id=user_id, folder_id=redirect_folder))


@mod.route('/users/<int:user_id>/folders/<int:folder_id>/pass/', methods=('POST',))
@roles_required('users')
def folder_pass(user_id, folder_id):
    folder = Folder.query.filter_by(user_id=user_id, id=folder_id).first_or_404()

    target_user_id = request.form['user_id']

    folder.user_id = target_user_id
    for tour in folder.tours:
        tour.user_id = target_user_id
        if tour.footage.user_id == user_id:
            tour.footage.user_id = target_user_id

    db.session.commit()

    return redirect(url_for('.tours', user_id=user_id))
