import uuid
import datetime

from flask import request, abort, current_app, url_for
from flask_login import current_user, login_required
from flask_babel import gettext

from . import mod, api_response
from .common import load_tour_view
from visual.core import redis


@mod.route('/joint', methods=('POST', ))
def post_joint():
    """
    POST /joint
    Создаёт комнату совместного просмотра туров
    Input:
    {
        "title": str
        "tour_id": int
        "password": str
    }
    """

    tour = load_tour_view(request.json.get('tour_id'))

    room_id = str(uuid.uuid4())
    key = 'joint.room.{}'.format(room_id)

    room = {
        'tour_id': tour.id,
        'created': datetime.datetime.now().isoformat()
    }
    if current_user.is_authenticated:
        room['created_by'] = current_user.id
    if request.json.get('title'):
        room['title'] = request.json.get('title')
    if request.json.get('password'):
        room['password'] = request.json.get('password')

    redis.hmset(key, room)
    redis.expire(key, 60 * 60 * 24 * 7)

    room['room_id'] = room_id
    room['url'] = url_for('front.joint_room', room_id=room_id)

    return api_response(room)


@mod.route('/joint/<room_id>', methods=('PUT', ))
@login_required
def put_joint(room_id):
    """
    PUT /joint/<room_id>
    {
        title: str
    }
    Меняет свойства комнаты. Работает, только если её создал текущий пользователь.
    """
    key = 'joint.room.{}'.format(room_id)
    room = redis.hgetall(key)
    if not room or not room.get('created_by') or room.get('created_by') != str(current_user.id):
        abort(403, gettext('You can\'t edit this room.'))

    if 'title' in request.json and isinstance(request.json['title'], str):
        room['title'] = request.json['title'].strip()
        redis.hmset(key, room)

    room['room_id'] = room_id
    room['url'] = url_for('front.joint_room', room_id=room_id)
    room.pop('password', None)
    return api_response(room)


@mod.route('/joint/<room_id>', methods=('DELETE', ))
@login_required
def delete_joint(room_id):
    """
    DELETE /joint/<room_id>
    Удаляет комнату room_id. Работает, только если её создал текущий пользователь.
    """
    key = 'joint.room.{}'.format(room_id)
    room = redis.hgetall(key)
    if not room or not room.get('created_by') or room.get('created_by') != str(current_user.id):
        abort(403, gettext('You can\'t delete this room.'))

    redis.delete(key)

    return '', 200
