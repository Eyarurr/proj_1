import os
import io
import json
import tempfile
import contextlib
import rq

from flask import abort, request, Response, current_app
from flask_babel import gettext
from flask_login import current_user
import datauri

from visual.core import db
from ..models import User, Footage, Tour, TourSeen


class BgJob:
    def __init__(self, job: rq.job.Job = None, queue: rq.queue.Queue = None, **kwargs):
        """
        job: rq.Job
        """
        if job is not None:
            self.status = job.get_status()
            self.id = job.id
        if queue is not None:
            self.queue_length = len(queue) + 1

        if 'id' in kwargs:
            self.id = kwargs['id']
        if 'status' in kwargs:
            self.status = kwargs['status']
        if 'queue_length' in kwargs:
            self.queue_length = kwargs['queue_length']
        self.eta = kwargs.get('eta')
        self.message = kwargs.get('message')

    def api_repr(self):
        r = {
            'id': self.id,
            'status': self.status,
            'queue_length': self.queue_length,
            'eta': self.eta,
            'message': self.message,
        }
        return r


class FieldsParam:
    """Класс для GET-параметров `fields`. Инициализируется строкой вида field1,field2,...,fieldN, поддерживает оператор in
    (if 'field2' in fields)
    """

    def __init__(self, data='default', shortcuts=None):
        """Инициализирует класс строкой data. В shortcuts можно указать "магические" свойства в виде {"default": ["id", "title"], ...}
        """
        self._data = set(data.split(','))
        if shortcuts:
            for field, expanded in shortcuts.items():
                if field in self._data:
                    self._data.remove(field)
                    self._data.update(expanded)

    def __contains__(self, item):
        return item in self._data


def try_coerce(value, type_, value_name):
    """Пытается привести значение `value` к типу `type` и в случае ошибки выбрасывает HTTP 400"""
    try:
        value = type_(value)
    except (ValueError, TypeError):
        abort(400, gettext('Bad data type for property %(property)s', property=value_name))

    return value


@contextlib.contextmanager
def handle_asset_param(value, key) -> (io.IOBase, str):
    """
    Пытается понять значение в теле запроса для какого-нибудь файла. Понимает форматы:
      "flow@TOKEN/filename"
      "flow@TOKEN/*" - вернёт os.scandir() этой директории
      "dataurl@data"
    Возвращает кортеж:
        FileStream к загруженным данным
        Полный путь к файлу или директории

    Работает как context manager.
    Выбрасывает ValueError, если в значении неверные данные

    Пример использования:
    if 'screen' in request.json:
        with handle_asset_param(request.json['screen'], 'screen') as (fh, *_):
            tour.screen = fh

    :param value: Значение свойства тела запроса
    :param key: Название свойства. Используется для формирования текстов ошибок
    :return: (io.IOBase, filename)
    """
    try:
        protocol, data = value.split('@', 2)
    except (ValueError, AttributeError) as e:
        raise ValueError(gettext('Malformed %(key)s value.', key=key))

    if protocol == 'flow':
        try:
            token, filename = data.split('/')
        except (ValueError, AttributeError) as e:
            raise ValueError(gettext('Malformed %(key)s value.', key=key))

        if filename == '*':
            src = os.path.join(current_app.config['FLOW_UPLOAD_TMP_DIR'], token)
            if not os.path.isdir(src):
                raise ValueError(gettext('Source directory %(token)s not found for %(key)s.', token=token, key=key))

            with os.scandir(src) as fh:
                yield fh, src
        else:
            src = os.path.join(current_app.config['FLOW_UPLOAD_TMP_DIR'], token, filename)
            if not os.path.isfile(src):
                raise ValueError(gettext('Source file %(token)s/%(filename)s not found for %(key)s.', token=token, filename=filename, key=key))

            with open(src, 'rb') as fh:
                yield fh, src

    elif protocol == 'dataurl':
        try:
            uri = datauri.DataURI(data)
        except ValueError as e:
            raise ValueError(gettext('Malformed %(key)s value.' + ' ' + str(e), key=key))

        fh = io.BytesIO(uri.data)
        yield fh, None
        fh.close()


def select_dict(obj, selector):
    """Возвращает элемент вложенного объекта по селектору (`prop.subprop.subsubprop`). Если элеемнт не нашёлся, выбрасывает KeyError."""
    path = selector.split('.')
    for part in path:
        obj = obj[part]
    return obj


def update_dict(obj, selector, value):
    """Изменяет значение вложенного объекта по селектору."""
    path = selector.split('.')
    for part in path[:-1]:
        if part not in obj:
            obj[part] = {}
        obj = obj[part]
    obj[path[-1]] = value


def delete_key_dict(obj, selector_chunked):
    """Удаляет значение вложенного объекта по селектору: key1.key2.
    """
    _key = selector_chunked.pop(0)
    if selector_chunked:
        try:
            return delete_key_dict(obj[_key], selector_chunked)
        except (TypeError, KeyError, ValueError):
            return abort(400, gettext("Malformed %(key)s value. ", key=_key))
    else:
        if not _key in obj:
            return abort(400, gettext("Malformed %(key)s value. ", key=_key))
        obj.pop(_key, None)




def apply_sort_to_query(q, sort_key, orders):
    """
    Применяет к Query `q` сортировку (order_by). В словаре `orders` лежат сортировки в виде {sort_key: Model.field, ...}.
    Вид сортировки передаётся в sort_key. Понимает `-` перед значением вида сортировки.
    Возвращает ту же модифицированную Query.
    """
    if not sort_key:
        abort(400, gettext('Unknown sort type "%(sort)s"', sort=sort_key))
    if sort_key[0] == '-':
        sort_key = sort_key[1:]
        sort_desc = True
    else:
        sort_desc = False

    if sort_key not in orders:
        abort(400, gettext('Unknown sort type "%(sort)s"', sort=sort_key))
    if sort_desc:
        order = orders[sort_key].desc().nullslast()
    else:
        order = orders[sort_key]
    q = q.order_by(order)

    return q


def apply_pagination_to_query(q, q_total=None, limit_default=50, limit_max=500):
    """
    Функция создаёт объект Response.pagination. Свойства offset и limit берёт из query string,
    приводя их к int. Значение limit ограничивается параметром limit_max.
    Эти значения применяются к BaseQuery `q`.
    Если в query string присутствует параметр `total`, а параметр функции `q_total` не равен None,
    то вычисляется общее количество объектов исходя из ожидания, что в `q_total` лежит BaseQuery
    для вычисления этого значения (вызовется `q_total.scalar()`)
    Возвращается кортеж `(q, pagination)` из модифицированной BaseQuery и объекта `Response.pagination`.
    """
    pagination = {
        'offset': request.args.get('offset', 0, type=int),
        'limit': request.args.get('limit', limit_default, type=int)
    }
    if pagination['offset']:
        q = q.offset(pagination['offset'])

    if pagination['limit'] > limit_max:
        pagination['limit'] = limit_max
    if pagination['limit']:
        q = q.limit(pagination['limit'])

    if q_total and request.args.get('total'):
        pagination['total'] = q_total.scalar()

    return q, pagination


def load_user_edit(user_id):
    """Загружает юзера для редактирования (если можно)."""
    if not current_user.is_authenticated:
        abort(401)

    if user_id is None or user_id == current_user.id:
        user = current_user
    else:
        user = User.query.get_or_404(user_id)
        if user.id != current_user.id:
            abort(403, gettext('You can not edit this user.'))

    return user


def load_tour_view(tour_id, required_types=None, required_statuses=None, load_seen=False):
    """Загружает тур для чтения с реляциями Tour.footage, Tour.user проверкой доступа"""
    def abort_password():
        """Функция аборта если не подошёл пароль (возвращает HTTP 403 + хедер X-Reason)"""
        abort(Response(
            json.dumps({'errors': [gettext('Wrong tour password.')]}),
            status=403,
            headers={'Content-Type': 'application/json', 'X-Reason': 'password'}
        ))

    q = db.session.query(Tour)

    q = q.join(Footage) \
        .options(db.contains_eager(Tour.footage)) \
        .options(db.joinedload(Tour.user))\
        .filter(Tour.id == tour_id)

    if load_seen and current_user.is_authenticated:
        q = q.add_columns(TourSeen).outerjoin(TourSeen, db.and_(TourSeen.tour_id == Tour.id, TourSeen.user_id == current_user.id))
        tour, seen = q.first_or_404(description='Tour not found.')
        tour.seen_by_me = seen
    else:
        tour = q.first_or_404(description='Tour not found.')

    if required_types and tour.footage.type not in required_types:
        abort(400, gettext('Wrong type of tour.'))

    if required_statuses and tour.footage.status not in required_statuses:
        abort(400, gettext('Wrong status of tour.'))

    # Проверка доступа. Админов не касается.
    if not current_user.is_authenticated:
        # Анонимам можно смотреть открытые туры (не hidden, не user.banned и не user.deleted)
        if tour.hidden or not tour.shareable():
            abort(403, 'You can not view this tour.')
        if tour.footage.status == 'banned':
            abort(403, 'This tour is blocked.')
        if tour.user.banned:
            abort(403, 'Owner of this tour has been banned.')
        if tour.user.deleted:
            abort(403, 'Owner of this tour has been deleted.')
        if tour.password_hash is not None:
            if not tour.check_password(request.args.get('password'), request.args.get('password_hash')):
                abort_password()
    elif current_user.has_role('tours'):
        # Админам можно всё
        pass
    elif tour.user_id == current_user.id:
        # Хозяину тура тоже можно всё
        pass
    else:
        # Остальным можно смотреть открытые туры
        if tour.hidden or not tour.shareable():
            abort(403, 'You can not view this tour.')
        if tour.footage.status == 'banned':
            abort(403, 'This tour is blocked.')
        if tour.user.banned:
            abort(403, 'Owner of this tour has been banned.')
        if tour.user.deleted:
            abort(403, 'Owner of this tour has been deleted.')
        if tour.password_hash is not None:
            if not tour.check_password(request.args.get('password'), request.args.get('password_hash')):
                abort_password()

    return tour


def load_tour_edit(tour_id, required_types=None, required_statuses=None):
    """Загружает тур для редактирования вместе с реляциями Tour.footage и Tour.user. Проверяет доступ."""
    tour = Tour.query\
        .options(db.joinedload(Tour.footage))\
        .options(db.joinedload(Tour.user))\
        .get_or_404(tour_id, description=gettext('Tour not found.'))

    if required_types and tour.footage.type not in required_types:
        abort(400, gettext('Wrong type of tour.'))

    if required_statuses and tour.footage.status not in required_statuses:
        abort(400, gettext('Wrong status of tour.'))

    # Проверка доступа.
    if not current_user.is_authenticated:
        # Анонимам нельзя нихуя
        abort(403, gettext('You can not edit this tour.'))
    elif current_user.has_role('tours'):
        # Админам можно всё
        pass
    elif tour.user_id == current_user.id:
        # Хозяину тура тоже можно всё
        pass
    else:
        # Остальным нельзя нихуя
        abort(403, gettext('You can not edit this tour.'))

    return tour


def load_footage_view(footage_id, required_types=None, required_statuses=None):
    """Загружает съёмку для просмотра (если можно)."""
    footage = Footage.query \
        .options(db.joinedload(Footage.user)) \
        .filter(Footage.id == footage_id) \
        .first_or_404(description=gettext('Footage not found.'))

    if required_types and footage.type not in required_types:
        abort(400, gettext('Wrong type of footage.'))

    if required_statuses and footage.status not in required_statuses:
        abort(400, gettext('Wrong status of footage.'))

    # Проверка доступа. Админов не касается.
    if not current_user.is_authenticated:
        # Анонимам можно смотреть открытые съёмки (не banned, не user.banned и не user.deleted)
        if footage.status == 'banned':
            abort(403, 'This tour is blocked.')
        if footage.user.banned:
            abort(403, 'Owner of this footage has been banned.')
        if footage.user.deleted:
            abort(403, 'Owner of this footage has been deleted.')
    elif current_user.has_role('tours'):
        # Админам можно всё
        pass
    elif footage.user_id == current_user.id:
        # Хозяину тура тоже можно всё
        pass
    else:
        # Остальным можно смотреть открытые туры
        if footage.status == 'banned':
            abort(403, 'You can not view this footage.')
        if footage.user.banned:
            abort(403, 'Owner of this footage has been banned.')
        if footage.user.deleted:
            abort(403, 'Owner of this footage has been deleted.')

    return footage


def load_footage_edit(footage_id, required_types=None, required_statuses=None) -> Footage:
    """Загружает съёмку для редактирования (если можно)."""
    footage = Footage.query\
        .options(db.joinedload(Footage.user)) \
        .filter(Footage.id == footage_id)\
        .first_or_404(description=gettext('Tour not found.'))

    if required_types and footage.type not in required_types:
        abort(400, gettext('Wrong type of footage.'))

    if required_statuses and footage.status not in required_statuses:
        abort(400, gettext('Wrong status of footage.'))

    # Проверка доступа.
    if not current_user.is_authenticated:
        # Анонимам нельзя нихуя
        abort(403, gettext('You can not edit this footage.'))
    elif current_user.has_role('tours'):
        # Админам можно всё
        pass
    elif footage.user_id == current_user.id:
        # Хозяину тура можно всё
        pass
    else:
        # Остальным нельзя нихуя
        abort(403, gettext('You can not edit this footage.'))

    return footage


def check_model_size(model_path, do_model_lowpoly):
    """Проверяет, может ли модель model_path быть такого размера с учётом того, будут её низкополигонализировать или нет.
    Если что, возвращает текст ошибки. Если всё ok, возвращает None.
    """
    model_size = os.stat(model_path).st_size
    limits = current_app.config['BUILDER_MODEL_SIZE_LIMIT']
    if model_size > limits[do_model_lowpoly]:
        if do_model_lowpoly:
            msg = gettext(
                'Uploaded model size %(uploaded)d MB exceeds maximum allowed size for high-poly '
                'models %(limit)d MB. Please consider optimizing it manually.',
                limit=limits[do_model_lowpoly] / 1024 ** 2, uploaded=model_size / 1024 ** 2
            )
        else:
            msg = gettext(
                'Uploaded model size %(uploaded)d MB exceeds maximum allowed size for low-poly '
                'models %(limit)d MB. Please consider using "Optimize 3d model" option to process it.',
                limit=limits[do_model_lowpoly] / 1024 ** 2, uploaded=model_size / 1024 ** 2
            )
        return msg
