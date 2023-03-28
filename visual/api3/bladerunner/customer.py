import datetime
import typing
import logging

from flask import request, abort, current_app
from flask_login import current_user, login_required
from flask_babel import gettext
from pydantic import BaseModel, conlist, validator, ValidationError, Extra, conint
import portion as P

from .geo import GeoRouter, GeoRouterError, GeoRouterExternalError
from visual.core import db
from visual.models import BROffice, BROperator, BROrder, BROrderAsset, SpaceTimePoint, City, Estate
from visual.api3 import mod, api_response
from visual.api3.common import apply_sort_to_query, apply_pagination_to_query


log = logging.getLogger('bladerunner')
log.setLevel(logging.DEBUG)


class GetFreetimeArgs(BaseModel):
    """Входные параметры Query String метода GET /bladerunner/freetime"""
    city_id: int
    date: datetime.date
    coords: conlist(float, min_items=2, max_items=2)
    tts: conint(gt=0)

    @validator('coords', pre=True)
    def split(cls, v):
        if isinstance(v, str):
            return v.split(',')
        return v


@mod.get('/bladerunner/freetime')
@login_required
def get_bladerunner_freetime():
    """
    GET /bladerunner/freetime
        ?city_id
        ?date
        ?coords
        ?tts
    Response:
        [[start_time, end_time], ...]
    """
    if 'bladerunner' not in current_user.products:
        abort(400, gettext('You have no access to %(product)s product.', product='bladerunner'))

    try:
        args = GetFreetimeArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    if args.date <= datetime.date.today():
        abort(400, gettext('There are no free operators in the past or today.'))

    # Работаем из предположения, что в городе один офис
    office = BROffice.query.filter_by(city_id=args.city_id, active=True).first_or_404(gettext('Sorry, we do not provide service in selected city.'))

    operators = BROperator.query.filter_by(office_id=office.id, active=True).all()
    if not operators:
        abort(400, gettext('No operators available in selected city.'))

    # Диапазоны подходящего времени начала съёмки, элементы - datetime.datetime
    suitable = P.empty()

    for operator in operators:
        for interval in operator.free_time_intervals(args.date):
            log.debug(f'OPERATOR {operator.user.id}: {interval}')

            # Длина всего временного интервала в минутах
            int_len = (interval.upper.time - interval.lower.time).seconds // 60

            try:
                # Время, чтобы доехать от точки начала до съёмки, если выезжаем в начале свободного интервала в минутах
                tta1 = GeoRouter(interval.lower.coords, args.coords, interval.lower.time).tta()
                if tta1 == -1:
                    abort(400, gettext('There is no route to selected location.'))

                # Время, чтобы доехать со съёмки до следующей точки, если выезжаем сразу после съёмки в минутах
                tta2 = GeoRouter(args.coords, interval.upper.coords, interval.lower.time + datetime.timedelta(minutes=args.tts)).tta()
                if tta2 == -1:
                    abort(400, gettext('There is no route to selected location.'))
            except GeoRouterError as e:
                current_app.logger.exception(e)
                abort(400, gettext('There was a problem calculating operator\'s route. Please try again later.'))

            # Полное время работы
            full_tts = tta1 + args.tts + tta2
            if full_tts > int_len:
                continue

            # Считаем диапазон времени, когда можно начать заказ
            free = P.closed(interval.lower.time + datetime.timedelta(minutes=tta1), interval.upper.time - datetime.timedelta(minutes=args.tts + tta2))

            suitable |= free

            log.debug(f'\n  dt_a:     {interval.lower.time}\n'
                      f'  dt_b:     {interval.upper.time}\n'
                      f'  int_len:  {int_len} ({int_len / 60}h)\n'
                      f'  tta1:     {tta1}\n'
                      f'  tts:      {args.tts}\n'
                      f'  tta2:     {tta2}\n'
                      f'  full_tts: {full_tts} ({full_tts / 60}h)\n'
                      f'  free:     {free.lower.timetz()} - {free.upper.timetz()}\n')

    log.debug(f'SUITABLE:\n{suitable}')

    result = [(x.lower, x.upper) for x in suitable]

    return api_response(result)


class PostOrderInput(BaseModel, extra=Extra.forbid):
    """Входные данные метода POST /bladerunner/orders"""
    city_id: int
    start: datetime.datetime
    tts: conint(gt=0)
    coords: conlist(float, min_items=2, max_items=2)
    address: str
    contacts: list = None
    customer_comment: str = None
    estate_id: int = None

    @validator('coords', pre=True)
    def split(cls, v):
        if isinstance(v, str):
            return v.split(',')
        return v


@mod.post('/bladerunner/orders')
@login_required
def post_bladerunner_orders():
    """
    POST /bladerunner/orders
    Input: {
        city_id: int
        start: datetime,
        tts: int,
        coords: [float, float],
        address: str,
        contacts: {},
        customer_comment
    }
    """
    if 'bladerunner' not in current_user.products:
        abort(400, gettext('You have no access to %(product)s product.', product='bladerunner'))

    try:
        inp = PostOrderInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    if inp.start.date() <= datetime.date.today():
        abort(400, gettext('You can not place order in the past or today.'))

    start = P.singleton(SpaceTimePoint(inp.coords, inp.start))
    log.debug(f'START: {start}')

    # Работаем из предположения, что в городе один офис
    office = BROffice.query.filter_by(city_id=inp.city_id, active=True).first_or_404(gettext('Sorry, we do not provide service in selected city.'))

    operators = BROperator.query.filter_by(office_id=office.id, active=True).all()
    if not operators:
        abort(400, gettext('No operators available in selected city.'))
    log.debug(f'OPERATORS: {operators}')

    # Список доступных операторов для заказа: кортежи (operator, tta1)
    candidates = []

    # Выбираем оператора, который может совершить заказ
    for operator in operators:
        free = operator.free_time_intervals(inp.start.date())
        log.debug(f'OPERATOR: {operator}')
        log.debug(f'FREE: {free}')
        # Проверяем, что начало заказа вообще попадает в свободный интервал
        if not (free & start):
            log.debug(f'  IS BUSY')
            continue

        # Проверяем, что оператор справится с заказом именно в это время
        for interval in free:
            # Ищем тот свободный интервал, куда попадает start:
            if not (interval & start):
                continue

            log.debug(f'  CHECKING INTERVAL {interval}')
            # Длина всего временного интервала в минутах
            int_len = (interval.upper.time - interval.lower.time).seconds // 60

            # Время, чтобы доехать от точки начала до съёмки, если выезжаем в указанное время
            try:
                tta1 = GeoRouter(interval.lower.coords, inp.coords, inp.start).tta()
                if tta1 == -1:
                    abort(400, gettext('There is no route to selected location.'))

                # Время, чтобы доехать со съёмки до следующей точки, если выезжаем сразу после съёмки в минутах
                tta2 = GeoRouter(inp.coords, interval.upper.coords, inp.start + datetime.timedelta(minutes=inp.tts)).tta()
                if tta2 == -1:
                    abort(400, gettext('There is no route to selected location.'))
            except GeoRouterError as e:
                current_app.logger.exception(e)
                abort(400, gettext('There was a problem calculating operator\'s route. Please try again later.'))

            # Полное время работы
            full_tts = tta1 + inp.tts + tta2

            log.debug(f'    int_len:  {int_len}')
            log.debug(f'    tta1:     {tta1}')
            log.debug(f'    tta2:     {tta2}')
            log.debug(f'    full_tts: {full_tts}')

            if full_tts > int_len:
                log.debug('  NO TIME: too long job')
                continue

            # Успеет ли приехать с предыдущего заказа?
            if interval.lower.time + datetime.timedelta(minutes=tta1) > inp.start:
                log.debug('  NO TIME: no time to arrive')
                continue

            # Успеет ли доехать до следующего заказа?
            if inp.start + datetime.timedelta(minutes=inp.tts + tta2) > interval.upper.time:
                log.debug('  NO TIME: no time for next order')
                continue

            candidates.append((operator, tta1))

    log.debug(f'CANDIDATES: {candidates}')
    if not candidates:
        abort(400, gettext('All operators are busy, please choose another time.'))

    # Выбираем ближайшего оператора
    candidates.sort(key=lambda x: x[1], reverse=True)
    operator = candidates[0][0]

    order = BROrder(
        status='scheduled',
        customer_id=current_user.id,
        office_id=operator.office_id,
        operator_id=operator.user_id,
        coords=inp.coords,
        address=inp.address,
        contacts=inp.contacts,
        start=inp.start,
        tts=inp.tts,
        customer_comment=inp.customer_comment
    )

    if inp.estate_id:
        estate = Estate.query.filter_by(user_id=current_user.id, id=inp.estate_id).first_or_404(gettext('Estate not found.'))
        order.estate_id = estate.id

    db.session.add(order)
    db.session.commit()

    return api_response(order.api_repr())


class PutOrderInput(BaseModel, extra=Extra.forbid):
    """Входные данные метода POST /bladerunner/orders"""
    status: str = None
    contacts: list = None
    customer_comment: str = None
    estate_id: int = None


@mod.put('/bladerunner/orders/<int:order_id>')
@login_required
def put_bladerunner_order(order_id):
    """"
    PUT /bladerunner/orders/<id>
    {status, contacts, customer_comment}
    """
    order = BROrder.query.filter(BROrder.customer_id == current_user.id, BROrder.id == order_id).first_or_404(gettext('Order not found.'))
    inp = PutOrderInput(**request.json)

    if inp.status:
        if order.status not in BROrder.STATUS_TRANSFORM['customer'] or inp.status not in BROrder.STATUS_TRANSFORM['customer'][order.status]:
            abort(400, gettext('You can not set this order status.'))
        order.status = inp.status

    if inp.contacts:
        log.debug(inp.contacts)
        order.contacts = inp.contacts

    if inp.customer_comment:
        order.customer_comment = inp.customer_comment

    if inp.estate_id:
        estate = Estate.query.filter_by(user_id=current_user.id, id=inp.estate_id).first_or_404(gettext('Estate not found.'))
        order.estate_id = estate.id

    db.session.commit()
    return api_response(order.api_repr())


class GetOrdersArgs(BaseModel):
    """Входные параметры Query String метода GET /bladerunner/orders"""
    status: typing.List[str] = None
    sort: str = '-created'
    assets:  typing.List[str] = None

    @validator('status', pre=True)
    def validate_status(cls, v):
        if isinstance(v, str):
            v = v.split(',')
        return v

    @validator('assets', pre=True)
    def validate_assets(cls, v):
        if isinstance(v, str):
            v = v.split(',')
        if set(v) - set(BROrderAsset.TYPES + ('*', )):
            raise ValueError('Bad asset type')
        return v


@mod.get('/bladerunner/orders')
@login_required
def get_bladerunner_orders():
    """
    GET /bladerunner/orders
    Отдаёт список заказов текущего юзера (customer_id == current_user.id)
    QueryString:
        ?status
        ?sort
        ?limit
        ?offset
        ?assets=types|*
    """
    if 'bladerunner' not in current_user.products:
        abort(400, gettext('You have no access to %(product)s product.', product='bladerunner'))

    try:
        args = GetOrdersArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    q = BROrder.query.filter(BROrder.customer_id == current_user.id)
    q_total = db.session.query(db.func.count(BROrder.id)).filter(BROrder.customer_id == current_user.id)

    # Фильтры
    if args.status:
        statuses = []
        for status in args.status:
            statuses += BROrder.resolve_status_wildcard(status)

        q = q.filter(BROrder.status.in_(statuses))
        q_total = q_total.filter(BROrder.status.in_(statuses))

    # Сортировка
    orders = {
        'created': BROrder.created,
        'start': BROrder.start,
        'status': BROrder.status,
        'tts': BROrder.tts,
        'address': BROrder.address,
    }
    q = apply_sort_to_query(q, args.sort, orders)
    q, pagination = apply_pagination_to_query(q, q_total)

    result = {}
    for order in q.all():
        result[order.id] = order.api_repr()

    # Подмешивание ассетов
    if args.assets:
        qa = BROrderAsset.query.join(BROrder).filter(BROrderAsset.order_id.in_(list(result.keys())), BROrder.status == 'success').order_by(BROrderAsset.created.desc())
        if '*' not in args.assets:
            qa = qa.filter(BROrderAsset.type.in_(args.assets))
        for asset in qa.all():
            result[asset.order_id].setdefault('assets', []).append(asset.api_repr())

    return api_response(list(result.values()), pagination=pagination)


@mod.get('/bladerunner/orders/<int:order_id>')
@login_required
def get_bladerunner_order(order_id):
    """
    GET /bladerunner/orders/<id>
    Отдаёт один заказ. Заказ должен принадлежать текущему юзеру.
    """
    if 'bladerunner' not in current_user.products:
        abort(400, gettext('You have no access to %(product)s product.', product='bladerunner'))

    order = BROrder.query.filter_by(customer_id=current_user.id, id=order_id).first_or_404(gettext('Order not found.'))

    if order.status == 'success':
        assets = []
        for asset in order.assets:
            assets.append(asset.api_repr())
        result = order.api_repr(assets=assets)
    else:
        result = order.api_repr()

    return api_response(result)


class GetOrderAssetsArgs(BaseModel):
    """Входные параметры Query String метода GET /bladerunner/orders/assets"""
    type: typing.List[str] = None
    sort: str = '-created'

    @validator('type', pre=True)
    def split(cls, v):
        if isinstance(v, str):
            return v.split(',')
        return v


@mod.get('/bladerunner/orders/<int:order_id>/assets')
@login_required
def get_bladerunner_order_assets(order_id):
    """
    GET /bladerunner/orders/<id>/assets
    Возвращает [BROrderAsset, ...]. Работает только для заказов в статусе `success`.
    QueryString:
        ?type - фильтр по типу, можно через запятую
        ?sort - сортировка, default=-created
        ?limit, ?offset
    """
    if 'bladerunner' not in current_user.products:
        abort(400, gettext('You have no access to %(product)s product.', product='bladerunner'))

    try:
        args = GetOrderAssetsArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    order = BROrder.query.filter_by(customer_id=current_user.id, id=order_id).first_or_404(gettext('Order not found.'))

    result = []

    if order.status != 'success':
        abort(400, gettext('Assets are available only for completed orders.'))

    q = BROrderAsset.query.filter_by(order_id=order.id)
    q_total = db.session.query(BROrderAsset.id).filter_by(order_id=order.id)

    if args.type:
        q = q.filter(BROrderAsset.type.in_(args.type))
        q_total = q_total.filter(BROrderAsset.type.in_(args.type))

    q = apply_sort_to_query(q, args.sort, {'created': BROrderAsset.created})
    q, pagination = apply_pagination_to_query(q, q_total)

    for asset in q.all():
        result.append(asset.api_repr())

    return api_response(result, pagination=pagination)


@mod.get('/bladerunner/cities')
@login_required
def get_bladerunner_cities():
    if 'bladerunner' not in current_user.products:
        abort(400, gettext('You have no access to %(product)s product.', product='bladerunner'))

    q = db.session.query(City).join(BROffice).filter(BROffice.active == True).order_by(City.name_en)

    if request.args.get('country_id'):
        q = q.filter(City.country_id == request.args['country_id'])

    result = []
    for city in q.all():
        result.append({'id': city.id, 'country_id': city.country_id, 'name': city.name})

    return api_response(result)
