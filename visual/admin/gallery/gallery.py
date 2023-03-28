import json

from flask import render_template, redirect, url_for, request, jsonify, flash, current_app as app

from visual.core import db
from visual.models import Tour, Footage, TourGalleryTag, Folder, User

from .. import mod, roles_required
from .forms import GalleryFilter


def set_tags_from_text(tour, text):
    """Устанавливает для тура tour список тегов из строки text, где лежит JSON списка [{'value': tag}, ... ].
    Совершает коммит."""
    TourGalleryTag.query.filter_by(tour_id=tour.id).delete(synchronize_session=False)
    if text.strip() != '':
        o = []
        for tag in json.loads(text):
            tag = tag['value'].strip().lower()
            if tag == '':
                continue
            o.append(TourGalleryTag(tour_id=tour.id, tag=tag))
        db.session.bulk_save_objects(o)
    db.session.commit()


def get_common_tags(popular=10):
    """Возвращает список тегов, используемых в фильтрах галереи и popular_tags прочих популярных тегов."""
    result = []

    # Теги, используемые в галерее
    for area in ('types', 'styles'):
        result += list(app.config['GALLERY_NAV_TAGS'][area].keys())

    # Добавим популярные теги
    if popular > 0:
        popular_tags = db.session.query(TourGalleryTag.tag)\
            .filter(~TourGalleryTag.tag.in_(result))\
            .group_by(TourGalleryTag.tag)\
            .order_by(db.func.count().desc())\
            .limit(popular)
        for tag in popular_tags:
            if tag.tag not in result:
                result.append(tag.tag)

    return list(result)


@mod.route('/gallery/')
def gallery():
    filters = GalleryFilter(request.args)
    mode = filters.mode.data
    if mode == '-':
        mode = None
    else:
        mode = int(mode)

    q = Tour.query \
        .join(Footage, Tour.footage_id == Footage.id) \
        .join(User, Tour.user_id == User.id) \
        .outerjoin(Folder, Tour.folder_id == Folder.id) \
        .filter(Footage.status == 'published', Footage.type.in_(['virtual', 'real']), Tour.hidden != True, User.deleted == None) \
        .filter(Tour.gallery_user == True) \
        .options(db.joinedload(Tour.gallery_tags), db.contains_eager(Tour.folder), db.contains_eager(Tour.user))

    if filters.tag.data:
        q = q.join(TourGalleryTag).filter(TourGalleryTag.tag == filters.tag.data)

    if filters.search.data:
        q = q.filter(Tour.title.ilike('%' + filters.search.data + '%'))

    if filters.sort.data == 'title':
        q = q.order_by(Folder.title, Tour.title)
    elif filters.sort.data == 'sort':
        q = q.order_by(Tour.gallery_sort.desc())
    else:
        q = q.order_by(Tour.created.desc())

    if mode == 1:
        # На вкладке "Галерея" также показываем туры с главной
        q = q.filter(Tour.gallery_admin >= mode)
    else:
        q = q.filter(Tour.gallery_admin == mode)

    tours = q.paginate(per_page=10, error_out=False)

    return render_template('admin/gallery/index.html', tours=tours, Tour=Tour, common_tags=get_common_tags(), filters=filters)


@mod.route('/gallery/<int:tour_id>/accept/', methods=('POST', ))
@roles_required('gallery')
def gallery_accept(tour_id):
    tour = Tour.query.get_or_404(tour_id)
    tour.gallery_admin = 1

    if request.form.get('featured'):
        tour.gallery_admin = 100

    if request.form.get('sendback'):
        gallery_sort = (db.session.query(db.func.min(Tour.gallery_sort)).filter(
            Tour.gallery_admin != 0).scalar() or 0) - 1
    else:
        gallery_sort = (db.session.query(db.func.max(Tour.gallery_sort)).filter(Tour.gallery_admin != 0).scalar() or 0) + 1
    tour.gallery_sort = gallery_sort

    db.session.commit()

    set_tags_from_text(tour, request.form['tags'])

    return redirect(url_for('.gallery', **request.args))


@mod.route('/gallery/<int:tour_id>/decline/', methods=('POST', ))
@roles_required('gallery')
def gallery_decline(tour_id):
    """Запрещает публикацию тура в галерее (gallery_admin=0).
    Если POST[folder'] == true, то также ставит gallery_admin=0 остальным немодерированным турам в папке.
    """
    tour = Tour.query.get_or_404(tour_id)

    if request.form.get('folder'):
        Tour.query\
            .filter_by(folder_id=tour.folder_id, gallery_user=True, gallery_admin=None)\
            .update({'gallery_admin': 0}, synchronize_session=False)
    else:
        tour.gallery_admin = 0

    db.session.commit()
    return redirect(url_for('.gallery', **request.args))


@mod.route('/gallery/<int:tour_id>/edit/', methods=('GET', 'POST', ))
@roles_required('gallery')
def gallery_edit(tour_id):
    tour = Tour.query.get_or_404(tour_id)

    if request.method == 'POST':
        tour.gallery_admin = request.form.get('gallery_admin')
        if tour.gallery_admin == 'None':
            tour.gallery_admin = None
        if not request.form.get('gallery_sort'):
            flash('Параметр "Порядковый номер" не указан!', 'danger')
            return redirect(url_for('.gallery', **request.args))

        tour.gallery_sort = request.form.get('gallery_sort')
        set_tags_from_text(tour, request.form['tags'])

        return redirect(url_for('.gallery', **request.args))
    else:
        result = {
            'tags': json.dumps([{'value': tag.tag} for tag in tour.gallery_tags]),
            'gallery_admin': tour.gallery_admin,
            'gallery_sort': tour.gallery_sort,
            'title': tour.title,
        }
        return jsonify(result)


@mod.route('/gallery/tags/')
def gallery_tags():
    filters = GalleryFilter(request.args)
    q = db.session.query(TourGalleryTag.tag, db.func.count())\
        .group_by(TourGalleryTag.tag)\
        .order_by(db.func.count().desc(), TourGalleryTag.tag)

    tags = q.paginate(per_page=50, error_out=False)

    return render_template('admin/gallery/tags.html', tags=tags, common_tags=get_common_tags(popular=0), filters=filters)


@mod.route('/gallery/tag-rename/', methods=('POST', ))
@roles_required('gallery')
def gallery_tag_rename():
    """Переименовывание тега. Вход (POST): oldname, newname."""

    oldname = request.form.get('oldname').strip()
    newname = request.form.get('newname').strip()

    TourGalleryTag.query.filter_by(tag=oldname).update({'tag': newname})
    db.session.commit()

    flash('Тег {} переименован в {}'.format(oldname, newname), 'success')
    return redirect(url_for('.gallery_tags'))
