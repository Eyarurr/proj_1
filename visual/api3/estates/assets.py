import typing

from flask import request, abort, current_app
from flask_login import current_user, login_required
from flask_babel import gettext
from pydantic import ValidationError
from sqlalchemy.orm.attributes import flag_modified
import boto3

from . import ASSETS_SORTS
from .. import mod, api_response
from ..common import apply_sort_to_query, handle_asset_param, BgJob
from .models import *
from visual.core import db, queue_quick
from visual.models import Estate, EstateTag, EstateAsset, Tag, User, Tour, TourVideo, BROrder, BROrderAsset


@mod.post('/estates/<int:estate_id>/assets')
@login_required
def post_estate_assets(estate_id):
    """
    POST /estates/<id>/assets
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    try:
        inp = PostAssetInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    if inp.type not in EstateAsset.TYPES:
        abort(400, f'Bad type: "{inp.type}"')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))

    asset = EstateAsset(
        estate_id=estate.id,
        type=inp.type
    )

    asset.title = inp.title
    asset.sort = inp.sort

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

    estate.cnt_assets.setdefault(asset.type, 0)
    estate.cnt_assets[asset.type] += 1
    flag_modified(estate, 'cnt_assets')

    db.session.commit()

    return api_response(asset.api_repr())


@mod.get('/estates/<int:estate_id>/assets')
@login_required
def get_estate_assets(estate_id):
    """
    GET /estates/<id>/assets
    """
    try:
        args = GetEstateAssetsArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    result = []

    q = EstateAsset.query.filter_by(estate_id=estate.id)
    if args.type:
        q = q.filter(EstateAsset.type.in_(args.type))
    q = apply_sort_to_query(q, args.sort, ASSETS_SORTS)
    for tag in q.all():
        result.append(tag.api_repr())

    return api_response(result)


@mod.get('/estates/<int:estate_id>/assets/<int:asset_id>')
@login_required
def get_estate_asset(estate_id, asset_id):
    """
    GET /estates/<id>/assets/<id>
    """
    asset = EstateAsset.query.join(Estate)\
        .filter(Estate.user_id == current_user.id, Estate.id == estate_id, EstateAsset.id == asset_id)\
        .first_or_404(gettext('Asset not found.'))

    return api_response(asset.api_repr())


@mod.put('/estates/<int:estate_id>/assets/<int:asset_id>')
@login_required
def put_estate_asset(estate_id, asset_id):
    """
    PUT /estates/<id>/assets/<id>
    """
    try:
        inp = PutEstateAssetInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    asset = EstateAsset.query.join(Estate)\
        .filter(Estate.user_id == current_user.id, Estate.id == estate_id, EstateAsset.id == asset_id)\
        .first_or_404(gettext('Asset not found.'))

    if inp.title:
        asset.title = inp.title
    if inp.sort is not None:
        asset.sort = inp.sort

    db.session.commit()

    return api_response(asset.api_repr())


@mod.delete('/estates/<int:estate_id>/assets/<int:asset_id>')
@login_required
def delete_estate_asset(estate_id, asset_id):
    """
    DELETE /estates/<id>/assets/<id>
    """
    asset, estate = db.session.query(EstateAsset, Estate)\
        .join(Estate)\
        .filter(Estate.user_id == current_user.id, Estate.id == estate_id, EstateAsset.id == asset_id)\
        .first_or_404(gettext('Asset not found.'))

    asset.delete_files()
    db.session.delete(asset)

    estate.cnt_assets.setdefault(asset.type, 0)
    estate.cnt_assets[asset.type] -= 1
    flag_modified(estate, 'cnt_assets')

    db.session.commit()

    return '', 204


@mod.delete('/estates/<int:estate_id>/assets')
@login_required
def delete_estate_assets(estate_id):
    """
    DELETE /estates/<id>/assets
    """
    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))

    q = EstateAsset.query.filter_by(estate_id=estate.id)

    # Удаляем файлы из S3. Вызывать EstateAsset.delete_files() в цикле для каждого ассета — медленно.
    objs = []
    for asset in q.all():
        if asset.s3key:
            objs.append({'Key': asset.s3key})
        if asset.preview_s3key:
            objs.append({'Key': asset.preview_s3key})
    if objs:
        s3 = boto3.resource('s3', endpoint_url=current_app.config['S3_ENDPOINT_URL'])
        s3bucket = s3.Bucket(current_app.config['S3_BUCKET'])
        s3bucket.delete_objects(Delete={'Objects': objs, 'Quiet': True})

    q.delete()
    estate.cnt_assets = {}

    db.session.commit()

    return '', 204


@mod.post('/estates/<int:estate_id>/assets/from-br-asset/<int:br_asset_id>')
@login_required
def post_estate_asset_from_br_asset(estate_id, br_asset_id):
    """
    POST /estates/<id>/assets/from-br-asset/<id>
    """
    try:
        args = PostAssetsFromBRAsset(**request.args)
        if current_app.config['ENV'] == 'production':
            args.force_synchronous = False
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    br_asset = BROrderAsset.query\
        .join(BROrder)\
        .filter(BROrder.customer_id == current_user.id, BROrder.status == 'success', BROrderAsset.id == br_asset_id)\
        .first_or_404(gettext('Asset not found.'))

    # Проверяем, нет ли среди ассетов Эстейта ассета, созданного из этого BROrderAsset
    if not request.args.get('ignore_existing'):
        existing = EstateAsset.query.filter_by(estate_id=estate.id, from_br_asset_id=br_asset.id).first()
        if existing:
            return api_response(existing.api_repr(), warnings=[gettext('This asset has already been copied.')])

    if not br_asset.is_heavy or args.force_synchronous:
        asset = estate.create_asset_from_brorderasset(br_asset)
        db.session.commit()
        return api_response(asset.api_repr())
    else:
        job = queue_quick.enqueue('visual.jobs.api.post_estates_asset_from_br_asset', estate.id, br_asset.id)
        return api_response(bgjobs=[BgJob(job, queue_quick).api_repr()])


@mod.post('/estates/<int:estate_id>/assets/from-br-order/<int:br_order_id>')
@login_required
def post_estate_asset_from_br_order(estate_id, br_order_id):
    """
    POST /estates/<id>/assets/from-br-asset/<id>
    """
    try:
        args = PostAssetsFromBROrder(**request.args)
        if current_app.config['ENV'] == 'production':
            args.force_synchronous = False
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    br_order = BROrder.query.filter_by(customer_id=current_user.id, status='success', id=br_order_id)\
        .first_or_404(gettext('Order not found.'))

    # Собираем списки BROrderAsset.id - кого добавить, кого пропустить - в add и skip
    q = BROrderAsset.query.filter_by(order_id=br_order.id)
    if args.type:
        q = q.filter(BROrderAsset.type.in_(args.type))
    add_sync = []
    add_async = []
    skip = []
    for br_asset in q.all():
        if not request.args.get('ignore_existing'):
            existing = EstateAsset.query.filter_by(estate_id=estate.id, from_br_asset_id=br_asset.id).first()
            if existing:
                skip.append(br_asset.id)
                continue
        if not br_asset.is_heavy or args.force_synchronous:
            add_sync.append(br_asset)
        else:
            add_async.append(br_asset)

    result = create_assets_from_brassets(estate, add_sync)
    warnings = None
    if skip:
        warnings = [gettext('%(skipped)d assets have already been copied.', skipped=len(skip))]
    bgjobs = None
    if add_async:
        job = queue_quick.enqueue('visual.jobs.api.post_estate_asset_from_br_order', estate.id, [x.id for x in add_async])
        if not job:
            abort(500, 'API: failed to enqueue job.')
        bgjobs = [BgJob(job, queue_quick).api_repr()]

    return api_response(result, warnings=warnings, bgjobs=bgjobs)


def create_assets_from_brassets(estate: Estate, bros: typing.List[BROrderAsset]):
    """Функция юзается как в методе API, так и в фоновой задаче."""
    result = []
    for br_asset in bros:
        asset = estate.create_asset_from_brorderasset(br_asset)
        db.session.add(asset)
        db.session.commit()
        result.append(asset.api_repr())

    return result
