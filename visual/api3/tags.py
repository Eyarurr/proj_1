from flask import request, abort, current_app
from flask_login import current_user, login_required
from flask_babel import gettext

from . import mod, api_response
from visual.core import db
from visual.models import Tag


@mod.post('/my/tags')
@login_required
def post_user_tag():
    """
    POST /my/tags
    {
        name
    }
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    if 'name' not in request.json or type(request.json['name']) is not str:
        abort(400, gettext('Required field "%(key)s" is missing.', key='name'))

    tag = Tag(user_id=current_user.id)

    tag.update_from_api_request(request.json)
    db.session.add(tag)
    db.session.commit()

    return api_response(tag.api_repr())


@mod.put('/my/tags/<int:tag_id>')
@login_required
def put_user_tag(tag_id):
    """
    POST /my/tags
    {
        name
    }
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    tag = Tag.query.filter_by(user_id=current_user.id, id=tag_id).first_or_404(gettext('Tag not found.'))

    tag.update_from_api_request(request.json)
    db.session.commit()

    return api_response(tag.api_repr())


@mod.get('/my/tags/<int:tag_id>')
@login_required
def get_user_tag(tag_id):
    """
    GET /my/tags/<id>
    """
    tag = Tag.query.filter_by(user_id=current_user.id, id=tag_id).first_or_404(gettext('Tag not found.'))

    return api_response(tag.api_repr())


@mod.get('/my/tags')
@login_required
def get_user_tags():
    """
    GET /my/tags
    """
    tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name).all()

    result = []
    for tag in tags:
        result.append(tag.api_repr())

    return api_response(result)


@mod.delete('/my/tags/<int:tag_id>')
@login_required
def delete_user_tag(tag_id):
    """
    GET /my/tags/<id>
    """
    tag = Tag.query.filter_by(user_id=current_user.id, id=tag_id).first_or_404(gettext('Tag not found.'))

    db.session.delete(tag)
    db.session.commit()

    return '', 204
