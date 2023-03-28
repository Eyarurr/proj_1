import datetime
import logging
import typing

from sqlalchemy.orm.attributes import flag_modified
from flask import request, abort, current_app
from flask_login import current_user, login_required
from flask_babel import gettext
from pydantic import BaseModel, conlist, validator, ValidationError, Extra
import boto3
import botocore

from .. import mod, api_response
from .customer import GetOrdersArgs
from visual.core import db
from visual.models import BROffice, BROperator, BROrder, SpaceTimePoint, City, BROrderAsset, Tour, TourVideo
from visual.api3.common import apply_sort_to_query, apply_pagination_to_query, handle_asset_param


log = logging.getLogger('bladerunner')
log.setLevel(logging.DEBUG)


class PutOrderInput(BaseModel, extra=Extra.forbid):
    """Входные данные метода PUT /bladerunner/operator/orders/<id>"""
    status: str = None
    operator_comment: str = None


@mod.put('/bladerunner/operator/orders/<int:order_id>')
@login_required
def put_bladerunner_operator_order(order_id):
    """
    PUT /bladerunner/operator/orders/<id>
    Input: {
        status: str
        operator_comment: str
    }
    """
    if not current_user.has_role('br.operator'):
        abort(400, gettext('You are not operator.'))

    try:
        inp = PutOrderInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    order = BROrder.query.filter_by(operator_id=current_user.id, id=order_id).first_or_404(gettext('Order not found.'))

    if inp.operator_comment is not None:
        order.operator_comment = inp.operator_comment

    if inp.status:
        if order.status not in BROrder.STATUS_TRANSFORM['operator'] or inp.status not in BROrder.STATUS_TRANSFORM['operator'][order.status]:
            abort(403, gettext('Status transition "%(was)s" -> "%(to)s" is not permitted', was=order.status, to=inp.status))
        order.status = inp.status

    db.session.commit()

    return api_response(order.api_repr('operator'))


class GetOperatorOrdersArgs(GetOrdersArgs):
    """Пока такие же, как и у кастомера - наследуем целиком"""
    pass


@mod.get('/bladerunner/operator/orders')
@login_required
def get_bladerunner_operator_orders():
    """
    GET /bladerunner/operator/orders
    Отдаёт список заказов текущего юзера (customer_id == current_user.id)
    QueryString:
        ?status
        ?sort
        ?limit
        ?offset
        ?assets=types|*

        @todo: функция очень похожа на аналогичную в customer.py, не юзать ли одну с разными route?
    """
    if not current_user.has_role('br.operator'):
        abort(400, gettext('You are not operator.'))

    try:
        args = GetOperatorOrdersArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    q = BROrder.query.filter(BROrder.operator_id == current_user.id, BROrder.status != 'smoking')
    q_total = db.session.query(db.func.count(BROrder.id)).filter(BROrder.operator_id == current_user.id, BROrder.status != 'smoking')

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
        qa = BROrderAsset.query.join(BROrder).filter(BROrderAsset.order_id.in_(list(result.keys()))).order_by(BROrderAsset.created.desc())
        if '*' not in args.assets:
            qa = qa.filter(BROrderAsset.type.in_(args.assets))
        for asset in qa.all():
            result[asset.order_id].setdefault('assets', []).append(asset.api_repr())

    return api_response(list(result.values()), pagination=pagination)


@mod.get('/bladerunner/operator/orders/<int:order_id>')
@login_required
def get_bladerunner_operator_order(order_id):
    """
    GET /bladerunner/operator/orders/<id>
    Отдаёт один заказ. Заказ должен принадлежать оператору-текущему юзеру
    """
    if not current_user.has_role('br.operator'):
        abort(400, gettext('You are not operator.'))

    order = BROrder.query.filter_by(operator_id=current_user.id, id=order_id).first_or_404(gettext('Order not found.'))

    assets = []
    for asset in order.assets:
        assets.append(asset.api_repr())

    return api_response(order.api_repr('operator', assets=assets))


class GetOrderAssetsArgs(BaseModel):
    """Входные параметры Query String метода GET /bladerunner/orders/assets"""
    type: typing.List[str] = None
    sort: str = '-created'

    @validator('type', pre=True)
    def split(cls, v):
        if isinstance(v, str):
            return v.split(',')
        return v


@mod.get('/bladerunner/operator/orders/<int:order_id>/assets')
@login_required
def get_bladerunner_operator_order_assets(order_id):
    """
    GET /bladerunner/operator/orders/<id>/assets
    Возвращает [BROrderAsset, ...].
    QueryString:
        ?type - фильтр по типу, можно через запятую
        ?sort - сортировка, default=-created
        ?limit, ?offset
    """
    if not current_user.has_role('br.operator'):
        abort(400, gettext('You are not operator.'))

    try:
        args = GetOrderAssetsArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    order = BROrder.query.filter_by(operator_id=current_user.id, id=order_id).first_or_404(gettext('Order not found.'))

    result = []

    if order.status == 'success':
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


class PutCheckinInput(BaseModel, extra=Extra.forbid):
    """Входные данные метода POST /bladerunner/operator/checkin"""
    coords: conlist(float, min_items=2, max_items=2)
    address: str

    @validator('coords', pre=True)
    def split(cls, v):
        if isinstance(v, str):
            return v.split(',')
        return v


@mod.post('/bladerunner/operator/checkin')
@login_required
def post_bladerunner_operator_checkin():
    """
    POST /bladerunner/operator/checkin
    Input: {
        status: str
        operator_comment: str
    }
    """
    if not current_user.has_role('br.operator'):
        abort(400, gettext('You are not operator.'))

    try:
        inp = PutCheckinInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    operator = BROperator.query.get_or_404(current_user.id, gettext('Can\'t find you as operator.'))

    order = BROrder(
        office_id=operator.office_id,
        operator_id=current_user.id,
        status='smoking',
        start=datetime.datetime.now(),
        tts=1,
        coords=inp.coords,
        address=inp.address
    )

    db.session.add(order)
    db.session.commit()

    return api_response(order.api_repr('operator'))


class PostAssetInput(BaseModel, extra=Extra.forbid):
    """Входные данные метода POST /bladerunner/operator/order/<id>/assets"""
    type: str
    tour_id: int = None
    tour_video_id: int = None
    url: str = None
    title: str = None
    product_meta: dict = None


@mod.post('/bladerunner/operator/orders/<int:order_id>/assets')
@login_required
def post_bladerunner_operator_assets(order_id):
    """
    POST /bladerunner/operator/orders/<id>/assets
    """
    if not current_user.has_role('br.operator'):
        abort(400, gettext('You are not operator.'))

    try:
        inp = PostAssetInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    if inp.type not in BROrderAsset.TYPES:
        abort(400, f'Bad type: "{inp.type}"')

    order = BROrder.query.filter_by(operator_id=current_user.id, id=order_id).first_or_404(gettext('Order not found.'))

    asset = BROrderAsset(
        order_id=order.id,
        operator_id=current_user.id,
        type=inp.type
    )

    asset.title = inp.title
    asset.product_meta = inp.product_meta

    if asset.type == 'tour':
        tour = Tour.query.get_or_404(inp.tour_id, gettext('Tour not found.'))
        asset.tour_id = tour.id
    elif asset.type == 'tour_video':
        tour_video = TourVideo.query.get_or_404(inp.tour_video_id, gettext('Video not found.'))
        asset.tour_video_id = tour_video.id
        asset.size = tour_video.size
        asset.width = tour_video.width
        asset.height = tour_video.height
    else:  # photo, plan, screenshot, video, other
        if inp.url is None:
            abort(400, 'API: specify url')
        try:
            with handle_asset_param(inp.url, 'url') as (fh, *_):
                asset.save_file(fh)

        except ValueError as e:
            abort(400, f'API: error processing asset: {e}.')

    db.session.add(asset)

    order.cnt_assets.setdefault(asset.type, 0)
    order.cnt_assets[asset.type] += 1
    flag_modified(order, 'cnt_assets')

    db.session.commit()

    return api_response(asset.api_repr())


@mod.delete('/bladerunner/operator/orders/<int:order_id>/assets/<int:asset_id>')
@login_required
def delete_bladerunner_operator_assets(order_id, asset_id):
    """
    POST /bladerunner/operator/orders/<id>/assets
    """
    if not current_user.has_role('br.operator'):
        abort(400, gettext('You are not operator.'))

    asset, order = db.session.query(BROrderAsset, BROrder)\
        .join(BROrder)\
        .filter(BROrder.operator_id == current_user.id, BROrder.id == order_id, BROrderAsset.id == asset_id)\
        .first_or_404(gettext('Asset not found.'))

    asset.delete_files()
    db.session.delete(asset)

    order.cnt_assets.setdefault(asset.type, 0)
    order.cnt_assets[asset.type] -= 1
    flag_modified(order, 'cnt_assets')

    db.session.commit()

    return '', 204
