import requests
import logging
import ast

from flask import request, abort, current_app
from flask_login import current_user, login_required
from flask_babel import gettext
import boto3
import botocore

from . import mod, api_response
from .common import load_tour_edit, apply_pagination_to_query
from visual.core import db
from visual.models import TourVideo


@mod.post('/tours/<tour_id>/videos')
@login_required
def post_tours_videos(tour_id):
    """
    POST /tours/<id>/videos
    {
        walk, duration, size, width, height, fps, title, preview, url
    }
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    # Проверяем, что тур есть и принадлежит текущему юзеру
    load_tour_edit(tour_id, required_types=['virtual', 'real'], required_statuses=['published', 'testing'])

    # Обязательные при создании поля
    for key in ('walk', 'video_s3_key'):
        if key not in request.json:
            abort(400, gettext('Required field "%(key)s" is missing.', key=key))

    video = TourVideo(
        user_id=current_user.id,
        tour_id=tour_id
    )
    video.update_from_api_request(request.json)

    db.session.add(video)
    db.session.commit()

    return api_response(video.api_repr())


@mod.put('/tours/<tour_id>/videos/<video_id>')
@login_required
def put_tours_video(tour_id, video_id):
    """
    PUT /tours/<id>/videos/<id>
    {
        walk, duration, size, width, height, fps, title, preview, url
    }
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    # Проверяем, что тур есть и принадлежит текущему юзеру
    load_tour_edit(tour_id, required_types=['virtual', 'real'], required_statuses=['published', 'testing'])

    video = TourVideo.query.filter_by(id=video_id, user_id=current_user.id, tour_id=tour_id).first_or_404(gettext('Video not found.'))
    video.update_from_api_request(request.json)
    db.session.commit()

    return api_response(video.api_repr())


@mod.get('/tours/<tour_id>/videos/<video_id>')
@login_required
def get_tours_video(tour_id, video_id):
    """
    GET /tours/<id>/videos/<id>
    """
    load_tour_edit(tour_id, required_types=['virtual', 'real'], required_statuses=['published', 'testing'])

    video = TourVideo.query.filter_by(id=video_id, tour_id=tour_id, user_id=current_user.id).first_or_404(gettext('Video not found.'))

    return api_response(video.api_repr())


@mod.get('/tours/<tour_id>/videos')
@login_required
def get_tours_videos(tour_id):
    """
    GET /tours/<id>/videos
    ?limit, ?offset
    """
    tour = load_tour_edit(tour_id, required_types=['virtual', 'real'], required_statuses=['published', 'testing'])
    # Небольшой хак дающий админам по ссылке видеть
    # список видео на вкладке медиа других пользователей
    if current_user.has_role('tours'):
        user_id = tour.user_id
    else:
        user_id = current_user.id

    q = TourVideo.query.filter_by(tour_id=tour_id, user_id=user_id).order_by(TourVideo.created.desc())
    q_total = db.session.query(db.func.count(TourVideo.id)).filter_by(tour_id=tour_id, user_id=user_id)

    q, pagination = apply_pagination_to_query(q, q_total)

    result = []
    for video in q.all():
        result.append(video.api_repr())

    return api_response(result, pagination=pagination)


@mod.get('/my/tours/videos')
@mod.get('/users/<user_id>/tours/videos')
@login_required
def get_user_videos(user_id=None):
    """
    GET /tours/<id>/videos
    ?limit, ?offset
    """
    if user_id is None:
        user_id = current_user.id
    if user_id != current_user.id:
        abort(403)

    q = TourVideo.query.filter_by(user_id=user_id).order_by(TourVideo.created.desc())
    q_total = db.session.query(db.func.count(TourVideo.id)).filter_by(user_id=user_id)

    q, pagination = apply_pagination_to_query(q, q_total)

    result = []
    for video in q.all():
        result.append(video.api_repr())

    return api_response(result, pagination=pagination)


@mod.delete('/tours/<tour_id>/videos/<video_id>')
@login_required
def delete_tours_video(tour_id, video_id):
    """
    DELETE /tours/<id>/videos/<id>
    """
    # Проверяем, что тур есть и принадлежит текущему юзеру
    load_tour_edit(tour_id, required_types=['virtual', 'real'], required_statuses=['published', 'testing'])

    video = TourVideo.query.filter_by(id=video_id, user_id=current_user.id, tour_id=tour_id).first_or_404(gettext('Video not found.'))
    db.session.delete(video)

    # Удаляем файлы из S3-хранилища
    try:
        s3 = boto3.resource('s3', endpoint_url=current_app.config['S3_ENDPOINT_URL'])
        s3bucket = s3.Bucket(current_app.config['S3_BUCKET'])
        response = s3bucket.delete_objects(
            Delete={
                'Objects': [
                    {
                        'Key': video.video_s3_key,
                        # 'VersionId': 'string'
                    },
                    {
                        'Key': video.preview_s3_key,
                        # 'VersionId': 'string'
                    },
                ],
                'Quiet': False
            }
        )
    except botocore.exceptions.ClientError:
        current_app.logger.exception('Failed to delete S3 objects in DELETE /tours/<id>/videos/<id>')

    db.session.commit()

    return '', 204


@mod.post('/tours/<tour_id>/videos/generate')
@login_required
def post_tours_video_generate(tour_id):
    """
    POST /tours/<id>/videos/generate {walk, width, height, fps}
    Отправляет запрос в API микросервиса Худайберген:
    POST {config.KHUDAIBERGEN_API_URL}/videos/tasks
    {
        tour_id,
        user_id,
        auth_token,
        walk, width, height, fps, autowalk_points
    }
    Возвращает ответ микросервиса.
    """
    if type(request.json) is not dict:
        abort(400, gettext('Malformed input.'))

    # Проверяем, что тур есть и принадлежит текущему юзеру
    tour = load_tour_edit(tour_id, required_types=['virtual', 'real'], required_statuses=['published', 'testing'])

    # Строим тело запроса
    body = {
        'tour_id': tour_id,
        'user_id': tour.user_id,
        'auth_token': str(current_user.get_valid_auth_token(create=True)),
        'autowalk_points': request.json.get('autowalk_points', None),
    }

    walk = request.json.get('walk')
    if walk not in ('auto', 'default'):
        abort(400, gettext('Malformed %(key)s value.', key='walk'))
    if walk == 'default' and ('walk' not in tour.meta or not tour.meta['walk']):
        abort(400, gettext('Tour does not contain saved route.'))
    body['walk'] = walk

    try:
        body['width'] = int(request.json.get('width', 1024))
        body['height'] = int(request.json.get('height', 768))
        body['fps'] = int(request.json.get('fps', 25))
    except (ValueError, KeyError, TypeError, AssertionError):
        abort(400, gettext('Malformed input data (width/height/fps error).'))

    # Ограничения width, height, fps
    if body['fps'] > 60 or body['fps'] <= 0:
        abort(400, gettext('FPS should be between 1 and 60.'))

    for dim in ('width', 'height'):
        if body[dim] < 608 or body[dim] > 1920:
            abort(400, gettext('Video %(dim)s should be between 608 and 1920 px.', dim=dim))

    if body['width'] + body['height'] > 3000:
        abort(400, gettext('Video width + height should be less than 3000.'))

    # Строим URL запроса
    query_string = {
        'client': 'biganto_server',
        'client_version': '1.0.0',
    }
    headers = {
        'Content-Type': 'application/json'
    }
    url = current_app.config['KHUDAIBERGEN_API_URL'] + '/videos/tasks'

    # Запрос!
    try:
        res = requests.request('POST', url, json=body, headers=headers, params=query_string)
    except requests.exceptions.RequestException as e:
        log = logging.getLogger('microservices')
        log.exception('Unable to send request to Khudaibergen microservice.')
        abort(400, gettext('Video recording service is temporarily unavailable. Please try again later.'))

    return res.json(), res.status_code
