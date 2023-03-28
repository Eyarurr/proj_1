from flask import request

from . import mod, api_response
from visual.core import db
from visual.models import User, Tour, Footage, TourGalleryTag, TourFeature
from .tours import tour_api_repr
from visual.front.gallery import GALLERY_CONDITIONS


def expand_fields(fields_param):
    fields = set(fields_param.split(','))
    if 'default' in fields:
        fields.remove('default')
        fields.update(['id', 'created', 'footage_id', 'hidden', 'title', 'preview', 'screen', 'gallery'])
    if 'gallery' in fields:
        fields.remove('gallery')
        fields.update(['gallery_user', 'gallery_admin', 'gallery_sort'])
    if 'traffic' in fields:
        fields.remove('traffic')
        fields.update(['traffic_today', 'traffic_total'])
    if 'baseurls' in fields:
        fields.remove('baseurls')
        fields.update(['tour_baseurl', 'footage_baseurl'])

    return fields


@mod.route('/gallery')
def get_gallery():
    """GET /gallery
    Получить туры из галереи.
    GET-параметры:
        ?offset:
        ?limit: default=16
        ?fields: default=default, default=id,footage.type,title,
        ?type:
        ?tag:
        ?feature: created, default, default=created
        ?sort
    Ответ:
        [Tour, ...]
    """
    offset = request.args.get('offset')
    limit = request.args.get('limit', type=int, default=16)
    type_ = request.args.get('type')
    tag = request.args.get('tag')
    feature = request.args.get('feature')
    sort = request.args.get('sort', default='created')
    fields = expand_fields(request.args.get('fields', 'default'))

    GALLERY_ORDERS = {
        'custom': (Tour.gallery_sort.desc(), Tour.id.desc()),
        'created': (Tour.created.desc(), Tour.id.desc())
    }

    # Строим запрос
    q = db.session.query(Tour) \
        .join(Footage, Tour.footage_id == Footage.id) \
        .join(User, Tour.user_id == User.id) \
        .filter(*GALLERY_CONDITIONS) \
        .order_by(*GALLERY_ORDERS[sort]) \
        .options(db.contains_eager(Tour.footage))

    if type_:
        q = q.filter(Footage.type == type_)

    if tag:
        q = q.join(TourGalleryTag)\
            .filter(TourGalleryTag.tag == tag) \
            .options(db.contains_eager(Tour.gallery_tags))
    else:
        q = q.options(db.joinedload(Tour.gallery_tags))

    if feature:
        q = q.join(TourFeature).filter(TourFeature.feature == feature)

    if offset:
        q = q.offset(offset)
    q = q.limit(limit)

    result = []
    warnings = []
    for tour in q.all():
        api_repr, warn = tour_api_repr(tour, fields)
        warnings += warn
        result.append(api_repr)

    return api_response(result, warnings=warnings)

