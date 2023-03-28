"""
Тесты методов API Умной Стройки: задачи.
"""
import pytest
import datetime

from visual import create_app
from visual.core import db
from visual.models import User, AuthToken, Footage, Tour

# Сторадж для передачи данных между тестами
MEMO = {
    # {email: User, ...}
    'users': {},
    # {id: Tour, ...}
    'tours': {},
    # {id: TourVideo, ...}
    'videos': {}
}


def create_users():
    """
    Создаёт юзеров:
    1. anna@biganto.com.
    2. boris@biganto.com.

    Возвращает словарь {email: {'id': User.id, 'name': User.name, 'email': User.email}, ...}
    """
    users = [
        {'id': 1, 'email': 'anna@biganto.com', 'name': 'Anna'},
        {'id': 2, 'email': 'boris@biganto.com', 'name': 'Boris'},
    ]
    result = {}
    for kwargs in users:
        user = User(email_confirmed=True, **kwargs)
        user.auth_tokens.append(
            AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30), ip='0.0.0.0')
        )
        db.session.add(user)
        db.session.flush()
        user.set_virtoaster_plan(100)
        result[user.email] = {'id': user.id, 'email': user.email, 'name': user.name}

    return result


def setup_module():
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        MEMO['users'] = create_users()

        tours = [
            # Хорошие.
            {'id': 1, 'user_id': 1, 'type': 'virtual', 'status': 'published'},  # Тут бы один распаковать настоящий, с маршрутом?
            {'id': 2, 'user_id': 2, 'type': 'real', 'status': 'testing'},  # Нет вшитого маршрута

            # Плохие
            {'id': 10, 'user_id': 2, 'type': 'outside', 'status': 'published'},
            {'id': 11, 'user_id': 2, 'type': 'virtual', 'status': 'loading'},
            {'id': 12, 'user_id': 2, 'type': 'virtual', 'status': 'processing'},
            {'id': 13, 'user_id': 2, 'type': 'virtual', 'status': 'banned'},
            {'id': 14, 'user_id': 2, 'type': 'virtual', 'status': 'published', 'meta': False},
        ]

        for src in tours:
            footage = Footage(id=src['id'], user_id=src['user_id'], type=src['type'], _status=src['status'])
            tour = Tour(id=src['id'], footage=footage, user_id=src['user_id'])
            if 'meta' in src:
                tour.meta = src['meta']
            db.session.add(footage)
            db.session.add(tour)

        db.session.commit()


@pytest.mark.bad_requests
def test_post_tour_videos_bad(api):
    """
    POST /tours/<id>/videos
    """
    # [(tour_id, auth_as, TourVideo), ...]
    bodies = [
        (1, 'anna@biganto.com', 'Я сделан из мяса'),  # Тело запроса — не объект
        (1, 'anna@biganto.com', {}),  # Пустое тело запроса
        (2, 'boris@biganto.com', {'walk': 'auto'}),    # Отсутствует URL
        (2, 'boris@biganto.com', {'url': 'https://a.ru/1.mp4'}),    # Отсутствует walk
        (10, 'boris@biganto.com', {'walk': 'auto', 'url': 'https://a.ru/1.mp4'}),  # outside
        (11, 'boris@biganto.com', {'walk': 'auto', 'url': 'https://a.ru/1.mp4'}),  # loading
        (12, 'boris@biganto.com', {'walk': 'auto', 'url': 'https://a.ru/1.mp4'}),  # processing
        (13, 'boris@biganto.com', {'walk': 'auto', 'url': 'https://a.ru/1.mp4'}),  # banned
        (1, 'anna@biganto.com', {'walk': 'тут либо default либо auto', 'url': 'https://a.ru/1.mp4'}),
        (1, 'anna@biganto.com', {'walk': 'default', 'duration': 'x', 'url': 'https://a.ru/1.mp4'}),
        (1, 'anna@biganto.com', {'walk': 'default', 'size': 'x', 'url': 'https://a.ru/1.mp4'}),
        (1, 'anna@biganto.com', {'walk': 'default', 'width': 'x', 'url': 'https://a.ru/1.mp4'}),
        (1, 'anna@biganto.com', {'walk': 'default', 'height': 'x', 'url': 'https://a.ru/1.mp4'}),
        (1, 'anna@biganto.com', {'walk': 'default', 'fps': 'x', 'url': 'https://a.ru/1.mp4'}),
    ]
    for tour_id, auth_as, body in bodies:
        resp = api.post(f'/tours/{tour_id}/videos', body, auth_as=auth_as)
        assert resp.status_code == 400, f'{tour_id} - {auth_as} - {body} - {resp.object}'


@pytest.mark.access
def test_post_tour_videos_access(api):
    # [(tour_id, auth_as, body), ...]
    bodies = [
        (5000, 'anna@biganto.com', {'walk': 'auto', 'url': 'https://a.ru/1.mp4'}),    # Несуществующий тур
        (2, 'anna@biganto.com', {'walk': 'auto'}),  # Чужой тур
        (1, None, {'walk': 'auto', 'url': 'https://a.ru/1.mp4'}),  # Без авторизации
    ]
    for tour_id, auth_as, body in bodies:
        resp = api.post(f'/tours/{tour_id}/videos', body, auth_as=auth_as)
        assert resp.status_code in (404, 403), '{}: {}'.format(body, resp.get_data(as_text=True))


def test_post_tour_videos_good(api):
    """
    POST /tours/<id>/videos/<id>
    Создаёт 3 видео:
    id | user  | tour_id | walk
    ---+-------+---------+---------
    1  | anna  | 1       | auto
    2  | anna  | 1       | default
    3  | boris | 2       | auto
    """
    # [(tour_id, auth_as, body), ...]
    bodies = [
        (
            1, 'anna@biganto.com',
            {'walk': 'auto', 'url': 'https://goatse.cx/1.mp4'}
        ),
        (
            1, 'anna@biganto.com',
            {
                'walk': 'default', 'title': 'Терпите, люди, скоро каникулы',
                'duration': 300, 'size': 400, 'width': 500, 'height': 600, 'fps': 30,
                'preview': 'https://goatse.cx/previews/2.jpg',
                'url': 'https://goatse.cx/videos/2.mp4',
            }
        ),
        (
            2, 'boris@biganto.com',
            {
                'walk': 'auto', 'title': 'Познание начинается с удивления',
                'duration': 30, 'size': 40, 'width': 50, 'height': 60, 'fps': 25,
                'preview': 'https://goatse.cx/previews/3.jpg',
                'url': 'https://goatse.cx/videos/3.mp4',
            }
        ),
    ]
    for tour_id, auth_as, body in bodies:
        resp = api.post(f'/tours/{tour_id}/videos', body, auth_as=auth_as)
        assert resp.status_code == 200, '{}: {}'.format(body, resp.object)
        assert resp.result
        assert 'id' in resp.result
        assert 'created' in resp.result
        assert resp.result['user_id'] == MEMO['users'][auth_as]['id']
        assert resp.result['tour_id'] == tour_id
        for k, v in body.items():
            assert resp.result.get(k) == v, k
        MEMO['videos'][resp.result['id']] = resp.result


@pytest.mark.bad_requests
def test_put_tour_videos_bad_requests(api):
    """
    PUT /tours/<id>/videos/<id>
    """
    # [(tour_id, video_id, auth_as, body), ...]
    bodies = [
        (1, 1, 'anna@biganto.com', 'Я сделан из мяса'),  # Тело запроса — не объект

        (2, 3, 'boris@biganto.com', {'walk': 'тут либо default либо auto', 'url': 'https://a.ru/1.mp4'}),
        (2, 3, 'boris@biganto.com', {'walk': 'default', 'duration': 'x', 'url': 'https://a.ru/1.mp4'}),
        (2, 3, 'boris@biganto.com', {'walk': 'default', 'size': 'x', 'url': 'https://a.ru/1.mp4'}),
        (2, 3, 'boris@biganto.com', {'walk': 'default', 'width': 'x', 'url': 'https://a.ru/1.mp4'}),
        (2, 3, 'boris@biganto.com', {'walk': 'default', 'height': 'x', 'url': 'https://a.ru/1.mp4'}),
        (2, 3, 'boris@biganto.com', {'walk': 'default', 'fps': 'x', 'url': 'https://a.ru/1.mp4'}),
    ]
    for tour_id, video_id, auth_as, body in bodies:
        resp = api.put(f'/tours/{tour_id}/videos/{video_id}', body, auth_as=auth_as)
        assert resp.status_code == 400, f'{tour_id} - {video_id} - {auth_as} - {body} - {resp.object}'


@pytest.mark.access
def test_put_tour_videos_access(api):
    """
    Проверяет доступ к методу PUT /tours/<id>/videos/<id>
    """
    # [(tour_id, video_id, auth_as, body), ...]
    bodies = [
        (1, 1, 'boris@biganto.com', {}),
        (5000, 1, 'anna@biganto.com', {}),  # Несуществующий тур
        (1, 3, 'anna@biganto.com', {}),  # Видео есть, но не в том туре
    ]
    for tour_id, video_id, auth_as, body in bodies:
        resp = api.put(f'/tours/{tour_id}/videos/{video_id}', body, auth_as=auth_as)
        assert resp.status_code in (403, 404), f'{tour_id} - {video_id} - {auth_as} - {body} - {resp.object}'


def test_put_tour_videos_good(api):
    """
    PUT /tours/<id>/videos/<id>
    """
    # [(tour_id, video_id, auth_as, body), ...]
    bodies = [
        (
            2, 3, 'boris@biganto.com',
            {
                'walk': 'default', 'title': 'Пустота возможна лишь как понятие в сознании человека: природа не терпит пустоты',
                'duration': 31, 'size': 41, 'width': 51, 'height': 61, 'fps': None,
                'preview': 'https://yandex.cx/previews/3.jpg',
                'url': 'https://yandex.cx/videos/3.mp4',
            }
        ),
    ]
    for tour_id, video_id, auth_as, body in bodies:
        resp = api.put(f'/tours/{tour_id}/videos/{video_id}', body, auth_as=auth_as)
        assert resp.status_code == 200, f'{tour_id} - {video_id} - {auth_as} - {body} - {resp.object}'
        assert resp.result
        assert resp.result['id'] == video_id
        assert 'created' in resp.result
        assert resp.result['user_id'] == MEMO['users'][auth_as]['id']
        assert resp.result['tour_id'] == tour_id
        for k, v in body.items():
            assert resp.result[k] == v, k
        MEMO['videos'][resp.result['id']] = resp.result


def test_get_tour_video(api):
    """
    GET /tours/<id>/videos/<id>
    """
    resp = api.get(f'/tours/1/videos/1', auth_as='anna@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result
    for k, v in resp.result.items():
        assert v == MEMO['videos'][1][k], k

    # Смотрим чужое видео
    resp = api.get(f'/tours/1/videos/1', auth_as='boris@biganto.com')
    assert resp.status_code in (403, 404), resp.object


def test_get_tour_videos(api):
    """
    GET /tours/<id>/videos
    """
    # Смотрим свои видео
    resp = api.get(f'/tours/1/videos', query_string={'total': 1}, auth_as='anna@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result
    assert len(resp.result) == 2
    assert resp.result[0]['id'] == 2
    assert resp.result[1]['id'] == 1
    assert resp.pagination
    assert resp.pagination['total'] == 2

    # Смотрим чужие видео
    resp = api.get(f'/tours/1/videos', auth_as='boris@biganto.com')
    assert resp.status_code in (403, 404), resp.object
    assert not resp.pagination or 'total' not in resp.pagination


def test_get_user_videos(api):
    """
    GET /my/tours/videos
    """
    # Смотрим свои видео
    resp = api.get(f'/my/tours/videos', query_string={'total': 1}, auth_as='anna@biganto.com')
    assert resp.status_code == 200, resp.object
    assert resp.result
    assert len(resp.result) == 2
    assert resp.result[0]['id'] == 2
    assert resp.result[1]['id'] == 1
    assert resp.pagination
    assert resp.pagination['total'] == 2


def test_delete_tour_video(api):
    # Удаляем не своё видео
    resp = api.delete(f'/tours/1/videos/1', auth_as='boris@biganto.com')
    assert resp.status_code == 403, resp.object

    resp = api.delete(f'/tours/1/videos/1', auth_as='anna@biganto.com')
    assert resp.status_code == 204, resp.object

    resp = api.get(f'/tours/1/videos/1', auth_as='anna@biganto.com')
    assert resp.status_code == 404

    resp = api.get(f'/tours/1/videos', auth_as='anna@biganto.com')
    assert resp.status_code == 200
    assert len(resp.result) == 1

