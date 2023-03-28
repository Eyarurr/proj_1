from flask import request, abort
from flask_login import current_user, login_required
from flask_babel import gettext
from sqlalchemy.orm.attributes import flag_modified

from visual.core import db
from visual.models import Tour, Footage
from visual.models.meta import TourMetaInside, NavigatorElement
from visual.util import get_flow_file
from . import mod, api_response
from .common import load_tour_edit, load_tour_view


@mod.route('/tours/<int:tour_id>/virtual/navigator')
def get_navigator(tour_id):
    """GET /tours/<tour_id>/virtual/navigator
    Возвращает навигатор
    """
    tour = load_tour_view(tour_id, required_types=['real', 'virtual'])

    return api_response(tour.meta.get('navigator'))


@mod.route('/tours/<int:tour_id>/virtual/navigator', methods=('POST', ))
def post_navigator(tour_id):
    """POST /tours/<tour_id>/virtual/navigator
    Добавляет элемент в навигатор.
    GET-параметры:
    - after: после какого элемента вставлять, по умолчанию - в конец
    """
    before = request.args.get('before', type=int)
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    elem = NavigatorElement(meta)
    warnings = elem.update_from_api_request(request.json)
    if before is not None:
        meta.navigator.insert(before, elem)
    else:
        meta.navigator.append(elem)

    meta.save_navigator()
    flag_modified(tour, 'meta')
    db.session.commit()

    return api_response(tour.meta['navigator'], warnings=warnings)


@mod.route('/tours/<int:tour_id>/virtual/navigator/<int:index>', methods=('PUT', ))
def put_navigator_item(tour_id, index):
    """
    Сохраняет элемент навигатора.
    """
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    if index >= len(meta.navigator):
        abort(404, gettext('Navigator item not found.'))

    warnings = meta.navigator[index].update_from_api_request(request.json)

    meta.save_navigator()
    flag_modified(tour, 'meta')
    db.session.commit()

    return api_response(tour.meta.get('navigator', [])[index], warnings=warnings)


@mod.route('/tours/<int:tour_id>/virtual/navigator', methods=('PUT', ))
def put_navigator(tour_id):
    """
    Сохраняет весь навигатор.
    """
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    meta.navigator = []
    warnings = []
    for nav_src in request.json:
        elem = NavigatorElement(meta)
        warnings += elem.update_from_api_request(nav_src)
        meta.navigator.append(elem)

    meta.save_navigator()
    flag_modified(tour, 'meta')
    db.session.commit()

    return api_response(tour.meta.get('navigator'), warnings=warnings)


@mod.route('/tours/<int:tour_id>/virtual/navigator/<int:index>', methods=('DELETE', ))
def delete_navigator_item(tour_id, index):
    """
    Удаляет элемент навигатора
    """
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    if index >= len(meta.navigator):
        abort(404, gettext('Navigator item not found.'))

    meta.navigator[index].delete_files()
    del meta.navigator[index]

    meta.save_navigator()
    flag_modified(tour, 'meta')
    db.session.commit()

    return api_response(tour.meta.get('navigator'))


@mod.route('/tours/<int:tour_id>/virtual/navigator', methods=('DELETE', ))
def delete_navigator(tour_id):
    """
    Удаляет элемент навигатора
    """
    tour = load_tour_edit(tour_id)
    meta = TourMetaInside(tour)

    for item in meta.navigator:
        item.delete_files()
    meta.navigator = []

    meta.save_navigator()
    flag_modified(tour, 'meta')
    db.session.commit()

    return '', 200
