"""
https://gitlab.biganto.com/p/docs/wikis/api3/joint
"""
import datetime

import pytest

from visual.core import redis
from visual import create_app
from visual.core import db
from visual.models import User, TeamMember, AuthToken, Tour, Footage

datasets = {
    'post_joint': [{'id': 1, 'body': {"tour_id": 'tour_id', "title": 'title_room', "password": None, }},
                   {'id': 2, 'body': {"tour_id": 'tour_id', "title": None, "password": None, }},
                   {'id': 3, 'body': {"tour_id": 'tour_id', "title": None, "password": 'password_for_joint', }},
                   ]
}

USERS = {}
TOURS = {}
ROOMS = {}


def setup_module():
    """
    Добавляем 5 юзеров, 1, 2, 3 - нормальные, 4 - забаненный и 5 - удалённый
    Всем, кроме 6 добавляем подписку virtoaster-trial.
    Создаем по одному туру и съемке каждому юзеру.
    :return:
    """
    app = create_app('config.test.py')
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.expire_on_commit = False

        users = [
            {'id': 1, 'name': 'anna', 'email': 'anna@biganto.com'},
            {'id': 2, 'name': 'boris', 'email': 'boris@biganto.com', 'team_member': TeamMember(roles=['tours'])},
            {'id': 3, 'name': 'super', 'email': 'super@biganto.com', 'password_hash': User.hash_password('123')},
            {'id': 4, 'name': 'banned', 'email': 'banned@biganto.com', 'banned': True},
            {'id': 5, 'name': 'deleted', 'email': 'deleted@biganto.com',
             'deleted': datetime.datetime.now() - datetime.timedelta(days=1)},
            {'id': 6, 'name': 'oleg', 'email': 'oleg@biganto.com'},
        ]
        for kwargs in users:
            user = User(email_confirmed=True, **kwargs)
            user.auth_tokens.append(
                AuthToken(signature=user.email, expires=datetime.datetime.now() + datetime.timedelta(days=30),
                          ip='0.0.0.0'))
            db.session.add(user)
            db.session.flush()
            if user.id != 6:
                user.set_virtoaster_plan(0)
            tour = Tour(user_id=user.id, title=f'tour_{user.id}',
                        footage=Footage(user_id=user.id, _status='testing', type='real'),
                        )
            db.session.add(tour)
            db.session.flush()

            USERS[user.id] = {k: getattr(user, k) for k in ('id', 'email', 'name', 'banned', 'deleted')}

        db.session.commit()
        db.session.close()


@pytest.mark.access
def test_access(api):

    # Описание: Пытаемся изменить комнату.
    # Параметры: Без токена авторизации
    # Ожидаемый результат: 403
    resp = api.put(f'/joint/1')
    assert resp.status_code == 403

    # Описание: Пытаемся удалить комнату.
    # Параметры: Без токена авторизации
    # Ожидаемый результат: 403
    resp = api.delete(f'/joint/1')
    assert resp.status_code == 403


def test_post_joint(api):
    """
    Создать комнату
    POST /joint

    тело
    {
    tour_id: int,  // ID тура для совместного просмотра
    title: str,    // Название комнаты. Если null, то используется название тура
    password: str // Если не null, то пароль для входа в комнату
    }
    """
    for user_id, user in USERS.items():
        tour_id = user_id
        ROOMS[tour_id] = []
        for dataset in datasets['post_joint']:
            dataset['body']['tour_id'] = tour_id

            # Описание: Пытаемся создать комнату.
            # Параметры: Без токена авторизации
            # Ожидаемый результат: Добавить комнату можно без авторизации
            # если у хозяина тура есть подписка 'virtoaster'
            resp = api.post('/joint', body=dataset['body'])
            if user['banned'] or user['deleted'] or user_id == 6:
                assert resp.status_code in (400, 403)
            else:
                assert resp.status_code == 200
                room = redis.hgetall(f'joint.room.{resp.result["room_id"]}')
                ROOMS[tour_id].append(resp.result["room_id"])
                # проверяем, что в редис создался ключ
                assert room

                # Если в теле есть title, то поверяем, что resp возвращает password и в редис есть title
                assert room.get('title', None) == dataset['body'].get('title', None) == resp.result.get('title', None)

                # Если в теле есть password, то поверяем, что resp возвращает password и в редис есть password
                assert room.get('password', None) == dataset['body'].get('password', None) == resp.result.get('password', None)

            # Описание: Пытаемся создать комнату.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: С авторизацией у комнаты появляется создатель - created_by
            resp = api.post('/joint', auth_as=user['email'], body=dataset['body'])
            if user['banned']:
                assert resp.status_code == 403
            else:
                room = redis.hgetall(f'joint.room.{resp.result["room_id"]}')
                ROOMS[tour_id].append(resp.result["room_id"])
                assert resp.status_code == 200
                # проверим, что есть параметр created_by
                assert int(room['created_by']) == int(resp.result['created_by'])


def test_put_joint(api):
    """
    Изменить свойства комнаты
    PUT /joint/<room_id>
    {
        title: str // Название комнаты
    }
    """
    for user_id, user in USERS.items():
        for room_id in ROOMS[user_id]:
            body = {'title': 'новое название комнаты'}

            # Описание: Пытаемся удалить комнату.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Любой авторизированный юзер может удалить свою комнату
            # (юзер является создателем комнаты)
            # если у хозяина тура есть подписка 'virtoaster'
            resp = api.put(f'/joint/{room_id}', auth_as=user['email'], body=body)
            room = redis.hgetall(f'joint.room.{room_id}')
            if room.get('created_by', None) and room.get('created_by', None) == str(user_id):
                assert resp.status_code == 200
                # Проверяем, что title комнаты поменялся
                assert room['title'] == resp.result['title'] == body['title']
            else:
                assert resp.status_code == 403


def test_delete_joint(api):
    """
    Удалить комнату
    DELETE /joint/<room_id>
    """
    for user_id, user in USERS.items():
        for room_id in ROOMS[user_id]:

            room = redis.hgetall(f'joint.room.{room_id}')
            # Описание: Пытаемся удалить комнату.
            # Параметры: С токеном авторизации
            # Ожидаемый результат: Авторизованный юзер может удалить свою комнату
            resp = api.delete(f'/joint/{room_id}', auth_as=user['email'])
            if room.get('created_by', None) and room.get('created_by', None) == str(user_id):
                assert resp.status_code == 200
                # Проверяем, что комнаты в редис нет
                assert not redis.hgetall(f'joint.room.{room_id}')
            else:
                assert resp.status_code == 403


@pytest.mark.bad_requests
def test_exceptions(api):
    """
    Плохие запросы
    """
    user_id = 3
    user = USERS[user_id]
    body = {"title": 'title_room', "password": None}

    # Описание: Пытаемся добавить комнату.
    # Параметры: не указан tour_id
    resp = api.post('/joint', body=body)
    assert resp.status_code == 404
    assert resp.has_error('Tour not found.')

    # Описание: Пытаемся изменить комнату.
    # Параметры: такого room_id не существует
    room_id = 123
    resp = api.put(f'/joint/{room_id}', auth_as=user['email'], body=body)
    assert resp.status_code == 403
    assert resp.has_error("You can't edit this room.")

    # Описание: Пытаемся удалить комнату.
    # Параметры: такого room_id не существует
    room_id = 123
    resp = api.delete(f'/joint/{room_id}', auth_as=user['email'])
    assert resp.status_code == 403
    assert resp.has_error("You can't delete this room.")
