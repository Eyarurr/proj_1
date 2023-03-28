from flask import request, jsonify, abort
from flask_login import current_user, login_required
from flask_babel import gettext

from . import mod, api_response
from visual.core import db
from visual.models import User, Folder, Tour


@mod.route('/users/<int:user_id>/folders')
@mod.route('/my/folders')
@login_required
def get_user_folders(user_id=None):
    """GET /users/<user_id>/folders
    Получить список папок пользователя.
    """
    if user_id is None:
        user = current_user
    else:
        user = User.query.get_or_404(user_id, description=gettext('User not found.'))

    if user.id != current_user.id:
        abort(403, gettext('You can not view folders of this user.'))

    q = db.session.query(Folder, db.func.count(Tour.id))\
        .outerjoin(Tour)\
        .filter(Folder.user_id == user.id)\
        .group_by(Folder.id)
    sorts = {
        'title': Folder.title,
        '-title': Folder.title.desc(),
        'created': Folder.created,
        '-created': Folder.created.desc()
    }
    q = q.order_by(sorts.get(request.args.get('sort'), Folder.title))

    result = []
    for folder, cnt_tours in q.all():
        f = folder.api_view(cnt_tours=cnt_tours)
        result.append(f)

    return api_response(result)


@mod.route('/users/<int:user_id>/folders', methods=('POST', ))
@mod.route('/my/folders', methods=('POST', ))
@login_required
def post_user_folders(user_id=None):
    """POST /users/<user_id>/folders
    Добавить папку пользователю.
    """
    if user_id is None:
        user = current_user
    else:
        user = User.query.get_or_404(user_id, description=gettext('User not found.'))

    if user.id != current_user.id:
        abort(403, gettext('You can not edit folders of this user.'))

    folder = Folder(user_id=user.id)

    title = request.json.get('title', '').strip()
    if not title:
        abort(400, gettext('Please specify folder title.'))
    folder.title = title

    db.session.add(folder)
    db.session.commit()

    return api_response(folder.api_view(cnt_tours=0))


@mod.route('/users/<int:user_id>/folders/<int:folder_id>')
@mod.route('/my/folders/<int:folder_id>')
@login_required
def get_user_folder(folder_id, user_id=None):
    """GET /users/<user_id>/folders/<folder_id>
    Получить папку пользователя.
    """
    if user_id is None:
        user = current_user
    else:
        user = User.query.get_or_404(user_id, description=gettext('User not found.'))

    if user.id != current_user.id:
        abort(403, gettext('You can not view folders of this user.'))

    folder = Folder.query.filter(Folder.user_id == user.id, Folder.id == folder_id).first_or_404(description=gettext('Folder not found.'))
    cnt_tours = db.session.query(db.func.count(Tour.id)).filter(Tour.folder_id == folder.id).scalar()

    return api_response(folder.api_view(cnt_tours=cnt_tours))


@mod.route('/users/<int:user_id>/folders/<int:folder_id>', methods=('PUT', ))
@mod.route('/my/folders/<int:folder_id>', methods=('PUT', ))
@login_required
def put_user_folder(folder_id, user_id=None):
    """PUT /users/<user_id>/folders/<folder_id>
    Сохранить папку."""
    if user_id is None:
        user = current_user
    else:
        user = User.query.get_or_404(user_id, description=gettext('User not found.'))

    if user.id != current_user.id:
        abort(403, gettext('You can not edit folders of this user.'))

    folder = Folder.query.filter(Folder.user_id == user.id, Folder.id == folder_id).first_or_404(description=gettext('Folder not found.'))
    cnt_tours = db.session.query(db.func.count(Tour.id)).filter(Tour.folder_id == folder.id).scalar()

    title = request.json.get('title', '').strip()
    if not title:
        abort(400, gettext('Please specify folder title.'))
    folder.title = title

    db.session.commit()

    return api_response(folder.api_view(cnt_tours=cnt_tours))


@mod.route('/users/<int:user_id>/folders/<int:folder_id>', methods=('DELETE',))
@mod.route('/my/folders/<int:folder_id>', methods=('DELETE',))
@login_required
def delete_user_folder(folder_id, user_id=None):
    """DELETE /users/<user_id>/folders/<folder_id>
    Удаляет папку. Туры в папке переместятся в корень (если нет параметра ?delete_tours)
    GET-параметры:
        ?delete_tours: Если параметр есть и не пустой, то удалить туры в папке, а не перемещать их в корень
    """
    if user_id is None:
        user = current_user
    else:
        user = User.query.get_or_404(user_id, description=gettext('User not found.'))

    if user.id != current_user.id:
        abort(403, gettext('You can not delete folders of this user.'))

    folder = Folder.query.filter(Folder.user_id == user.id, Folder.id == folder_id).first_or_404(description=gettext('Folder not found.'))

    if request.args.get('delete_tours'):
        for tour in folder.tours:
            tour.delete()

    db.session.delete(folder)
    db.session.commit()

    return '', 204
