
from flask import request, abort
from flask_login import current_user, login_required
from flask_babel import gettext
from pydantic import ValidationError

from .models import GetEstateTagsArgs, PutEstatesTagsInput, PostEstatesTagsInput
from .. import mod, api_response
from visual.core import db
from visual.models import Estate, EstateTag, Tag


@mod.get('/estates/<int:estate_id>/tags')
@login_required
def get_estate_tags(estate_id):
    """
    GET /estates/<id>/tags
    Параметры Query String:
        name: name=area,floor
        format_values=1
        group_tags=id|name
    """
    try:
        args = GetEstateTagsArgs(**request.args)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    q = EstateTag.query.filter(EstateTag.estate_id == estate.id)

    result = [] if args.group_tags is None else {}
    if args.name:
        q = q.join(Tag).filter(Tag.name.in_(args.name))

    for e_tag in q.all():
        if args.group_tags == 'id':
            result.setdefault(e_tag.tag_id, []).append(e_tag.api_repr(_format_value=args.format_values))
        elif args.group_tags == 'name':
            result.setdefault(e_tag.tag.name, []).append(e_tag.api_repr(_format_value=args.format_values))
        else:
            result.append(e_tag.api_repr(_format_value=args.format_values))
    return api_response(result)


@mod.get('/estates/<int:estate_id>/tags/<int:tag_id>')
@mod.get('/estates/<int:estate_id>/tags/<tag_name>')
@login_required
def get_estate_tag(estate_id, tag_id=None, tag_name=None):
    """
    GET /estates/<id>/tags/<id|name>
    """
    result = []
    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))

    q = db.session.query(EstateTag).filter(EstateTag.estate_id == estate.id)
    if tag_id:
        tag = q.filter(EstateTag.id == tag_id).first_or_404(gettext('Tag not found.'))
        result = tag.api_repr()
    elif tag_name:
        q = q.join(Tag).filter(Tag.name == tag_name)
        for tag in q.all():
            result.append(tag.api_repr())

    return api_response(result)


@mod.put('/estates/<int:estate_id>/tags/<int:tag_id>')
@login_required
def put_estate_tag(estate_id, tag_id):
    """
    PUT /estates/<id>/tags/<id>
    {value}
    """
    try:
        inp = PutEstatesTagsInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')
    
    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    e_tag = db.session.query(EstateTag).filter_by(id=tag_id, estate_id=estate.id).first_or_404(gettext('Tag not found.'))
    e_tag.value = inp.value
    db.session.add(e_tag)
    db.session.commit()
    return api_response(e_tag.api_repr())


@mod.post('/estates/<int:estate_id>/tags')
@login_required
def post_estate_tags(estate_id):
    """
    POST /estates/<id>/tags
    {name, value}
    """
    try:
        inp = PostEstatesTagsInput(**request.json)
    except ValidationError as e:
        return abort(400, f'API: bad input: {e}')

    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    tag = Tag.query.filter(Tag.user_id == current_user.id, Tag.name == inp.name).first_or_404(gettext('Tag not found.'))
    e_tag = EstateTag(estate_id=estate.id, tag_id=tag.id, value=inp.value)

    db.session.add(e_tag)
    db.session.commit()
    return api_response(e_tag.api_repr())


@mod.delete('/estates/<int:estate_id>/tags/<int:tag_id>')
@login_required
def delete_estate_tags_by_id(estate_id, tag_id):
    """
    DELETE /estates/<id>/tags/<id>
    """
    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    e_tag = db.session.query(EstateTag).filter_by(id=tag_id, estate_id=estate.id).first_or_404(gettext('Tag not found.'))
    db.session.delete(e_tag)
    db.session.commit()
    return '', 204


@mod.delete('/estates/<int:estate_id>/tags/<tag_name>')
@login_required
def delete_estate_tags_by_name(estate_id, tag_name):
    """
    DELETE /estates/<id>/tags/<name>
    """
    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))
    q = db.session.query(EstateTag).join(Tag).filter(EstateTag.estate_id == estate.id, Tag.name == tag_name)
    for e_tag in q.all():
        db.session.delete(e_tag)
        db.session.commit()
    return '', 204


@mod.delete('/estates/<int:estate_id>/tags')
@login_required
def delete_estate_tags(estate_id):
    """
    DELETE /estates/<id>/tags/<name>
    """
    estate = Estate.query.filter_by(user_id=current_user.id, id=estate_id).first_or_404(gettext('Estate not found.'))

    EstateTag.query.filter_by(estate_id=estate.id).delete()
    db.session.commit()

    return '', 204
