import typing
import re

from flask import request, abort
from flask_login import current_user, login_required
from flask_babel import gettext
from pydantic import ValidationError

from . import ASSETS_SORTS, TFilter
from .. import mod, api_response
from ..common import apply_sort_to_query, apply_pagination_to_query
from .models import *
from visual.core import db
from visual.models import Estate, EstateTag, EstateAsset, Tag, User


def process_tags_input(inp: typing.List[TagInput], estate: Estate, user: User):
    """
    Процессит часть тела запроса с тегами и добавляет их в `estate`
    """
    usertags = {}
    for tag in Tag.query.filter_by(user_id=user.id):
        usertags[tag.name] = tag

    add = []
    change = {}

    for itag in inp:
        if itag.id:
            change[itag.id] = itag.value
        elif itag.name:
            tag = usertags.get(itag.name)
            if not tag:
                abort(400, gettext('Tag "%(name)s" does not exist.', name=itag.name))
            add.append(EstateTag(tag=tag, value=itag.value))
        else:
            abort(400, 'API: tag should contain either id, either name.')

    if add:
        estate.tags += add

    if change:
        for etag_id, value in change.items():
            EstateTag.query.filter_by(id=etag_id).update({'value': value})


@mod.post('/my/estates')
@login_required
def post_estate():
    """
    POST /my/estates
    {
        title, remote_id, tags
    }
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    try:
        inp = PostEstatesInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate(user_id=current_user.id, title=inp.title)
    if inp.remote_id:
        estate.remote_id = inp.remote_id

    if inp.tags:
        process_tags_input(inp.tags, estate, current_user)

    db.session.add(estate)
    db.session.commit()

    # Формируем Estate.tags для ответа
    # Обрати внимание, дорогой разраб. EstateTag.api_repr() ожидает, что реляция EstateTag.tag уже загружена, иначе
    # она будет лазить в базу за каждым self.tag: Tag. Тэги у нас уже загружены в process_tags_input() и там же добавлены
    # EstateTag(tag=tag). Однако сессия же, блять, инвалидируется после коммита, и грузануть их придётся заново!
    tags = []
    q = EstateTag.query.options(db.joinedload(EstateTag.tag)).filter_by(estate_id=estate.id)
    for tag in q.all():
        tags.append(tag.api_repr())

    return api_response(estate.api_repr('owner', tags=tags))


@mod.put('/estates/<estate_id>')
@login_required
def put_estate(estate_id):
    """
    PUT /estates/<id>
    {
        title, remote_id, tags
    }
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    try:
        inp = PutEstatesInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))

    if inp.title:
        estate.title = inp.title
    if inp.remote_id:
        estate.remote_id = inp.remote_id

    if inp.tags:
        # estate.tags = []
        process_tags_input(inp.tags, estate, current_user)

    db.session.commit()

    tags = []
    q = EstateTag.query.options(db.joinedload(EstateTag.tag)).filter_by(estate_id=estate.id)
    for tag in q.all():
        tags.append(tag.api_repr())

    return api_response(estate.api_repr('owner', tags=tags))


@mod.get('/estates/<estate_id>')
@login_required
def get_estate(estate_id):
    """
    GET /estates/<id>
    """
    try:
        args = GetEstatesArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))

    result = estate.api_repr('owner')

    # Грузим теги, если надо
    if args.tags:
        q = EstateTag.query.join(Tag).options(db.contains_eager(EstateTag.tag))
        if args.tags != ['*']:
            q = q.filter(Tag.name.in_(args.tags))
        q = q.filter(EstateTag.estate_id == estate.id)

        for tag in q.all():
            if args.group_tags == 'id':
                result.setdefault('tags', {}).setdefault(tag.tag_id, []).append(tag.api_repr(_format_value=args.format_values))
            elif args.group_tags == 'name':
                result.setdefault('tags', {}).setdefault(tag.tag.name, []).append(tag.api_repr(_format_value=args.format_values))
            else:
                result.setdefault('tags', []).append(tag.api_repr(_format_value=args.format_values))

    # Грузим ассеты, если надо
    if args.assets:
        q = EstateAsset.query
        if args.assets != ['*']:
            q = q.filter(EstateAsset.type.in_(args.assets))
        q = q.filter(EstateAsset.estate_id == estate.id)

        q = apply_sort_to_query(q, args.assets_sort, ASSETS_SORTS)
        for asset in q.all():
            result.setdefault('assets', []).append(asset.api_repr())

    return api_response(result)


@mod.get('/my/estates')
@login_required
def get_estates():
    """
    GET /my/estates
    """
    try:
        args = GetEstatesArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    q = Estate.query.filter_by(user_id=current_user.id)
    q_total = db.session.query(db.func.count(Estate.id)).filter_by(user_id=current_user.id)

    # Сортировка
    q = apply_sort_to_query(q, args.sort, {
        'created': Estate.created,
        'synced': Estate.synced,
        'title': Estate.title
    })

    # ?tfilter
    if args.tfilter:
        try:
            tfilter = TFilter(args.tfilter)
            q = tfilter.apply_to_query(q)
            q_total = tfilter.apply_to_query(q_total)
        except ValueError as e:
            abort(400, f'API: {e}')

    q, pagination = apply_pagination_to_query(q, q_total)

    result = {}
    for estate in q.all():
        result[estate.id] = estate.api_repr('owner')

    # Грузим теги, если надо
    if args.tags:
        q = EstateTag.query.join(Tag).options(db.contains_eager(EstateTag.tag))
        if args.tags != ['*']:
            q = q.filter(Tag.name.in_(args.tags))
        q = q.filter(EstateTag.estate_id.in_(list(result.keys())))
        for tag in q.all():
            if args.group_tags == 'id':
                result[tag.estate_id].setdefault('tags', {}).setdefault(tag.tag_id, []).append(tag.api_repr(_format_value=args.format_values))
            elif args.group_tags == 'name':
                result[tag.estate_id].setdefault('tags', {}).setdefault(tag.tag.name, []).append(tag.api_repr(_format_value=args.format_values))
            else:
                result[tag.estate_id].setdefault('tags', []).append(tag.api_repr(_format_value=args.format_values))

    # Грузим ассеты, если надо
    if args.assets:
        q = EstateAsset.query
        if args.assets != ['*']:
            q = q.filter(EstateAsset.type.in_(args.assets))
        q = q.filter(EstateAsset.estate_id.in_(list(result.keys())))
        q = apply_sort_to_query(q, args.assets_sort, ASSETS_SORTS)
        for asset in q.all():
            result[asset.estate_id].setdefault('assets', []).append(asset.api_repr())

    return api_response(list(result.values()), pagination=pagination)


@mod.delete('/estates/<int:estate_id>')
@login_required
def delete_estate(estate_id):
    """
    GET /estates/<id>
    """
    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))

    # Стираем файлы ассетов
    for asset in estate.assets:
        asset.delete_files()

    db.session.delete(estate)
    db.session.commit()

    return '', 204


@mod.get('/my/estates/tags/ranges')
@login_required
def get_estates_tags_ranges():
    """
    GET /my/estates/tags/ranges
    """
    try:
        args = GetEstatesTagsRanges(**request.args)
    except ValidationError as e:
        return abort(400, f'API: {e}')

    q = db.session\
        .query(Tag.name, db.func.min(db.func.graceful_int(EstateTag.value)), db.func.max(db.func.graceful_int(EstateTag.value)))\
        .select_from(EstateTag)\
        .join(Tag)\
        .join(Estate)\
        .filter(Estate.user_id == current_user.id)\
        .group_by(Tag.id)

    if args.tags:
        q = q.filter(Tag.name.in_(args.tags))

    result = {}
    for tag_name, vmin, vmax in q.all():
        result[tag_name] = {'min': vmin, 'max': vmax}

    return api_response(result)
